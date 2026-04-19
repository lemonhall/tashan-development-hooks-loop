import json
from pathlib import Path


def make_repo(root: Path) -> None:
  (root / "hooks").mkdir(parents=True)
  (root / "hooks" / "stop_v_task_classifier.py").write_text("print('hook v1')\n", encoding="utf-8")
  (root / "hooks" / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
  (root / "hooks" / ".env.example").write_text("OPENAI_API_KEY=replace-me\n", encoding="utf-8")
  (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
  (root / "uv.lock").write_text("lock-v1\n", encoding="utf-8")


def test_sync_files_copies_only_changed_files(tmp_path: Path):
  from scripts.install_global_stop_hook import sync_project_files

  source = tmp_path / "repo"
  target = tmp_path / "global"
  make_repo(source)
  target.mkdir()
  (target / "stop_v_task_classifier.py").write_text("print('old')\n", encoding="utf-8")
  (target / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")

  result = sync_project_files(source, target, dry_run=False)

  assert result.copied == ["stop_v_task_classifier.py", ".env.example", "pyproject.toml", "uv.lock"]
  assert result.unchanged == [".env"]
  assert (target / "stop_v_task_classifier.py").read_text(encoding="utf-8") == "print('hook v1')\n"
  assert (target / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=secret\n"


def test_sync_files_dry_run_does_not_write(tmp_path: Path):
  from scripts.install_global_stop_hook import sync_project_files

  source = tmp_path / "repo"
  target = tmp_path / "global"
  make_repo(source)
  target.mkdir()

  result = sync_project_files(source, target, dry_run=True)

  assert "stop_v_task_classifier.py" in result.copied
  assert not (target / "stop_v_task_classifier.py").exists()


def test_hooks_json_is_unchanged_when_command_is_already_correct(tmp_path: Path):
  from scripts.install_global_stop_hook import ensure_hooks_json

  hooks_json = tmp_path / "hooks.json"
  command = 'python "C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\stop_v_task_classifier.py"'
  hooks_json.write_text(
    json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}),
    encoding="utf-8",
  )
  before = hooks_json.read_text(encoding="utf-8")

  result = ensure_hooks_json(hooks_json, command, dry_run=False, force=False)

  assert result.changed is False
  assert result.backup_path is None
  assert hooks_json.read_text(encoding="utf-8") == before


def test_hooks_json_replaces_only_hello_world_command(tmp_path: Path):
  from scripts.install_global_stop_hook import ensure_hooks_json

  hooks_json = tmp_path / "hooks.json"
  old_command = 'python "C:\\Users\\lemon\\.codex\\hooks\\hello_world.py"'
  new_command = 'python "C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\stop_v_task_classifier.py"'
  hooks_json.write_text(
    json.dumps({
      "hooks": {
        "Stop": [
          {
            "hooks": [
              {"type": "command", "command": old_command},
              {"type": "command", "command": "python other.py"},
            ],
          }
        ]
      }
    }),
    encoding="utf-8",
  )

  result = ensure_hooks_json(hooks_json, new_command, dry_run=False, force=False)
  data = json.loads(hooks_json.read_text(encoding="utf-8"))

  assert result.changed is True
  assert result.backup_path is not None
  assert result.backup_path.exists()
  assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == new_command
  assert data["hooks"]["Stop"][0]["hooks"][1]["command"] == "python other.py"


def test_hooks_json_adds_command_without_replacing_unrelated_stop_command(tmp_path: Path):
  from scripts.install_global_stop_hook import ensure_hooks_json

  hooks_json = tmp_path / "hooks.json"
  existing_command = "python other.py"
  new_command = 'python "C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\stop_v_task_classifier.py"'
  hooks_json.write_text(
    json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": existing_command}]}]}}),
    encoding="utf-8",
  )

  result = ensure_hooks_json(hooks_json, new_command, dry_run=False, force=False)
  data = json.loads(hooks_json.read_text(encoding="utf-8"))
  commands = [item["command"] for item in data["hooks"]["Stop"][0]["hooks"]]

  assert result.changed is True
  assert commands == [new_command, existing_command]


def test_hooks_json_replaces_legacy_target_venv_command_for_same_hook(tmp_path: Path):
  from scripts.install_global_stop_hook import ensure_hooks_json

  hooks_json = tmp_path / "hooks.json"
  old_command = '"C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\.venv\\Scripts\\python.exe" "C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\stop_v_task_classifier.py"'
  new_command = 'python "C:\\Users\\lemon\\.codex\\hooks\\stop_v_task_classifier\\stop_v_task_classifier.py"'
  hooks_json.write_text(
    json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": old_command}]}]}}),
    encoding="utf-8",
  )

  result = ensure_hooks_json(hooks_json, new_command, dry_run=False, force=False)
  data = json.loads(hooks_json.read_text(encoding="utf-8"))
  commands = [item["command"] for item in data["hooks"]["Stop"][0]["hooks"]]

  assert result.changed is True
  assert commands == [new_command]


def test_build_hook_command_uses_plain_python_launcher(tmp_path: Path):
  from scripts.install_global_stop_hook import build_hook_command

  command = build_hook_command(tmp_path / "global")

  assert '".venv\\Scripts\\python.exe"' not in command
  assert command == f'python "{tmp_path / "global" / "stop_v_task_classifier.py"}"'


def test_dependencies_sync_runs_only_when_dependency_files_changed(tmp_path: Path):
  from scripts.install_global_stop_hook import sync_dependencies_if_needed

  calls = []
  target = tmp_path / "global"
  target.mkdir()

  changed = sync_dependencies_if_needed(
    target,
    dependency_files_changed=True,
    dry_run=False,
    runner=lambda command: calls.append(command),
  )

  unchanged = sync_dependencies_if_needed(
    target,
    dependency_files_changed=False,
    dry_run=False,
    runner=lambda command: calls.append(command),
  )

  assert changed is False
  assert unchanged is False
  assert calls == []


def test_run_smoke_validates_hook_json_output(tmp_path: Path):
  from scripts.install_global_stop_hook import run_smoke

  source = tmp_path / "repo"
  target = tmp_path / "global"
  target.mkdir(parents=True)
  (source / "tests" / "fixtures").mkdir(parents=True)
  (source / "tests" / "fixtures" / "stop_payload_doc_done.json").write_text('{"last_assistant_message":"x"}', encoding="utf-8")
  (target / "stop_v_task_classifier.py").write_text("pass\n", encoding="utf-8")

  calls = []

  class Result:
    def __init__(self, stdout: str):
      self.stdout = stdout

  output = run_smoke(
    target,
    source,
    runner=lambda command, payload: (
      calls.append((command, payload)),
      Result('{"continue": true, "systemMessage": "hello"}')
    )[1],
  )

  assert output["continue"] is True
  assert calls == [
    (["py", "-3.13", str(target / "stop_v_task_classifier.py")], b'{"last_assistant_message":"x"}')
  ]
