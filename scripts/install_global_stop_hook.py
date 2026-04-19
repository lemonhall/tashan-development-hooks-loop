from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence


PROJECT_FILES = {
  Path("hooks/stop_v_task_classifier.py"): Path("stop_v_task_classifier.py"),
  Path("hooks/.env"): Path(".env"),
  Path("hooks/.env.example"): Path(".env.example"),
  Path("pyproject.toml"): Path("pyproject.toml"),
  Path("uv.lock"): Path("uv.lock"),
}

DEPENDENCY_FILES = {"pyproject.toml", "uv.lock"}
DEFAULT_TARGET = Path.home() / ".codex" / "hooks" / "stop_v_task_classifier"
DEFAULT_HOOKS_JSON = Path.home() / ".codex" / "hooks.json"
GLOBAL_PYTHON_VERSION = "3.13"


@dataclass
class SyncResult:
  copied: list[str] = field(default_factory=list)
  unchanged: list[str] = field(default_factory=list)
  missing: list[str] = field(default_factory=list)

  @property
  def dependency_files_changed(self) -> bool:
    return any(name in DEPENDENCY_FILES for name in self.copied)


@dataclass
class HooksJsonResult:
  changed: bool
  backup_path: Path | None = None
  reason: str = ""


def repo_root() -> Path:
  return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def files_equal(left: Path, right: Path) -> bool:
  if not left.exists() or not right.exists():
    return False
  if left.stat().st_size != right.stat().st_size:
    return False
  return sha256_file(left) == sha256_file(right)


def sync_project_files(source_root: Path, target_root: Path, *, dry_run: bool) -> SyncResult:
  result = SyncResult()

  if not dry_run:
    target_root.mkdir(parents=True, exist_ok=True)

  for source_relative, target_relative in PROJECT_FILES.items():
    source = source_root / source_relative
    target = target_root / target_relative
    display_name = target_relative.as_posix()

    if not source.exists():
      result.missing.append(source_relative.as_posix())
      continue

    if files_equal(source, target):
      result.unchanged.append(display_name)
      continue

    result.copied.append(display_name)
    if dry_run:
      continue

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

  return result


def build_hook_command(target_root: Path) -> str:
  hook_script = target_root / "stop_v_task_classifier.py"
  return f'python "{hook_script}"'


def backup_hooks_json(hooks_json: Path) -> Path:
  timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
  backup_path = hooks_json.with_name(f"{hooks_json.name}.bak-{timestamp}")
  shutil.copy2(hooks_json, backup_path)
  return backup_path


def load_hooks_json(hooks_json: Path) -> dict:
  if not hooks_json.exists():
    return {"hooks": {}}
  return json.loads(hooks_json.read_text(encoding="utf-8"))


def find_stop_command_hook(data: dict) -> dict | None:
  stop_groups = data.get("hooks", {}).get("Stop")
  if not isinstance(stop_groups, list):
    return None

  for group in stop_groups:
    hooks = group.get("hooks") if isinstance(group, dict) else None
    if not isinstance(hooks, list):
      continue
    for hook in hooks:
      if isinstance(hook, dict) and hook.get("type") == "command":
        return hook

  return None


def iter_stop_command_hooks(data: dict) -> list[dict]:
  stop_groups = data.get("hooks", {}).get("Stop")
  if not isinstance(stop_groups, list):
    return []

  command_hooks: list[dict] = []
  for group in stop_groups:
    hooks = group.get("hooks") if isinstance(group, dict) else None
    if not isinstance(hooks, list):
      continue
    for hook in hooks:
      if isinstance(hook, dict) and hook.get("type") == "command":
        command_hooks.append(hook)
  return command_hooks


def is_stop_v_task_classifier_command(command: str) -> bool:
  return "stop_v_task_classifier.py" in command


def ensure_hooks_json(
  hooks_json: Path,
  expected_command: str,
  *,
  dry_run: bool,
  force: bool,
) -> HooksJsonResult:
  data = load_hooks_json(hooks_json)
  data.setdefault("hooks", {})
  stop_groups = data["hooks"].setdefault("Stop", [{"hooks": []}])
  if not isinstance(stop_groups, list) or not stop_groups:
    data["hooks"]["Stop"] = [{"hooks": []}]
    stop_groups = data["hooks"]["Stop"]

  first_group = stop_groups[0]
  if not isinstance(first_group, dict):
    first_group = {"hooks": []}
    stop_groups[0] = first_group
  first_group.setdefault("hooks", [])

  command_hooks = iter_stop_command_hooks(data)
  same_hook_refs: list[tuple[list[dict], int, dict]] = []
  for group in stop_groups:
    hooks = group.get("hooks") if isinstance(group, dict) else None
    if not isinstance(hooks, list):
      continue
    for index, hook in enumerate(hooks):
      if not isinstance(hook, dict) or hook.get("type") != "command":
        continue
      command = str(hook.get("command", ""))
      if is_stop_v_task_classifier_command(command):
        same_hook_refs.append((hooks, index, hook))

  matching_hook = next((hook for _, _, hook in same_hook_refs if hook.get("command") == expected_command), None)
  if matching_hook is not None and len(same_hook_refs) == 1 and not force:
    return HooksJsonResult(changed=False, reason="already configured")

  hello_world_hook = next(
    (hook for hook in command_hooks if "hello_world.py" in str(hook.get("command", ""))),
    None,
  )

  if same_hook_refs:
    first_hooks, _, first_hook = same_hook_refs[0]
    first_hook["command"] = expected_command
    for hooks, index, _ in reversed(same_hook_refs[1:]):
      del hooks[index]
    reason = "updated stop_v_task_classifier stop command hook"
  elif hello_world_hook is not None:
    hello_world_hook["command"] = expected_command
    reason = "replaced hello_world stop command hook"
  elif force and command_hooks:
    command_hooks[0]["command"] = expected_command
    reason = "force updated stop command hook"
  else:
    first_group["hooks"].insert(0, {"type": "command", "command": expected_command})
    reason = "added stop command hook"

  if dry_run:
    return HooksJsonResult(changed=True, reason=f"dry-run: {reason}")

  backup_path = backup_hooks_json(hooks_json) if hooks_json.exists() else None
  hooks_json.parent.mkdir(parents=True, exist_ok=True)
  hooks_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
  return HooksJsonResult(changed=True, backup_path=backup_path, reason=reason)


def sync_dependencies_if_needed(
  target_root: Path,
  *,
  dependency_files_changed: bool,
  dry_run: bool,
  runner: Callable[[list[str]], object] | None = None,
) -> bool:
  return False


def default_smoke_runner(command: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
  return subprocess.run(command, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def run_smoke(
  target_root: Path,
  source_root: Path,
  *,
  runner: Callable[[list[str], bytes], object] | None = None,
) -> dict:
  fixture = source_root / "tests" / "fixtures" / "stop_payload_doc_done.json"
  hook_script = target_root / "stop_v_task_classifier.py"
  payload = fixture.read_bytes()
  command = ["py", f"-{GLOBAL_PYTHON_VERSION}", str(hook_script)]
  if runner is None:
    result = default_smoke_runner(command, payload)
  else:
    result = runner(command, payload)

  stdout = getattr(result, "stdout", "")
  if isinstance(stdout, bytes):
    stdout = stdout.decode("utf-8")
  output = json.loads(str(stdout).strip())
  if "continue" not in output:
    raise RuntimeError("Smoke output missing continue field")
  return output


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Install or refresh the global Codex Stop hook.")
  parser.add_argument("--source", type=Path, default=repo_root(), help="Project root to install from.")
  parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Global hook target directory.")
  parser.add_argument("--hooks-json", type=Path, default=DEFAULT_HOOKS_JSON, help="Codex hooks.json path.")
  parser.add_argument("--dry-run", action="store_true", help="Show actions without writing files.")
  parser.add_argument("--smoke", action="store_true", help="Run docs fixture through installed hook after syncing.")
  parser.add_argument("--force-hooks-json", action="store_true", help="Refresh Stop command even if it already matches.")
  return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
  args = parse_args(sys.argv[1:] if argv is None else argv)
  source_root = args.source.resolve()
  target_root = args.target.resolve()
  hooks_json = args.hooks_json.resolve()

  sync_result = sync_project_files(source_root, target_root, dry_run=args.dry_run)
  print(f"Target: {target_root}")
  print(f"Hook command: {build_hook_command(target_root)}")
  print(f"Copied: {', '.join(sync_result.copied) if sync_result.copied else 'none'}")
  print(f"Unchanged: {', '.join(sync_result.unchanged) if sync_result.unchanged else 'none'}")
  if sync_result.missing:
    print(f"Missing source files: {', '.join(sync_result.missing)}", file=sys.stderr)
    return 1

  sync_dependencies_if_needed(
    target_root,
    dependency_files_changed=sync_result.dependency_files_changed,
    dry_run=args.dry_run,
  )
  print("Dependencies: global Python mode (no target .venv sync)")

  hooks_result = ensure_hooks_json(
    hooks_json,
    build_hook_command(target_root),
    dry_run=args.dry_run,
    force=args.force_hooks_json,
  )
  print(f"hooks.json: {hooks_result.reason}")
  if hooks_result.backup_path is not None:
    print(f"hooks.json backup: {hooks_result.backup_path}")

  if args.smoke:
    if args.dry_run:
      print("Smoke: skipped during dry-run")
    else:
      run_smoke(target_root, source_root)
      print("Smoke: passed")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
