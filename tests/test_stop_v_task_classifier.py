import json
import io
import subprocess
import sys
from pathlib import Path


def test_gitignore_ignores_real_env():
  content = Path(".gitignore").read_text(encoding="utf-8")
  assert "hooks/.env" in content
  assert "hooks/stop_v_task_classifier.log" in content


def test_env_example_contains_required_keys():
  content = Path("hooks/.env.example").read_text(encoding="utf-8")
  assert "OPENAI_API_KEY=" in content
  assert "OPENAI_BASE_URL=" in content
  assert "OPENAI_MODEL=" in content


def test_extract_last_assistant_message_returns_string():
  from hooks.stop_v_task_classifier import extract_last_assistant_message

  payload = {
    "hook_event_name": "Stop",
    "last_assistant_message": "文档已经写到目标目录了，PRD、v1-index 和 v1 计划都已经落盘。",
  }

  assert extract_last_assistant_message(payload) == "文档已经写到目标目录了，PRD、v1-index 和 v1 计划都已经落盘。"


def test_build_hook_output_returns_block_reason_for_doc_done():
  from hooks.stop_v_task_classifier import DOCS_REVIEW_CONTINUATION_PROMPT, build_hook_output

  output = build_hook_output([
    {
      "classifier_id": "v_doc_writing_done",
      "is_match": True,
      "version": "v1",
      "milestone_id": "M1",
      "reason": "docs saved",
    },
  ])

  assert output == {
    "continue": True,
    "decision": "block",
    "reason": DOCS_REVIEW_CONTINUATION_PROMPT,
  }


def test_build_hook_output_skips_docs_continuation_when_stop_hook_active():
  from hooks.stop_v_task_classifier import build_hook_output

  output = build_hook_output(
    [
      {
        "classifier_id": "v_doc_writing_done",
        "is_match": True,
        "version": "v1",
        "milestone_id": None,
        "reason": "docs saved",
      },
    ],
    stop_hook_active=True,
  )

  assert output == {"continue": True}


def test_classifier_definitions_include_milestone_done():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS

  assert "v_milestone_done" in CLASSIFIER_DEFINITIONS


def test_classifier_prompts_support_tashan_completion_signal():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS

  for classifier_id in [
    "v_doc_writing_done",
    "v_milestone_done",
    "v_task_fully_done",
  ]:
    prompt = CLASSIFIER_DEFINITIONS[classifier_id]["prompt"]
    assert "TASHAN_COMPLETION_SIGNAL_BEGIN" in prompt
    assert "TASHAN_COMPLETION_SIGNAL_END" in prompt
    assert "tashan_status" in prompt
    assert "signal" in prompt.lower()


def test_build_hook_output_returns_milestone_message_for_m_done():
  from hooks.stop_v_task_classifier import build_hook_output

  output = build_hook_output([
    {
      "classifier_id": "v_doc_writing_done",
      "is_match": False,
      "version": "v1",
      "milestone_id": "M2",
      "reason": "not docs",
    },
    {
      "classifier_id": "v_milestone_done",
      "is_match": True,
      "version": "v1",
      "milestone_id": "M2",
      "reason": "M2 complete",
    },
    {
      "classifier_id": "v_task_fully_done",
      "is_match": False,
      "version": "v1",
      "milestone_id": "M2",
      "reason": "v1 still has M3",
    },
  ])

  assert output == {
    "continue": True,
    "systemMessage": "hello World from hooks, on stop event, and v milestone has done",
  }


class FakeResponse:
  def __init__(self, output_text: str):
    self.output_text = output_text


class FakeResponsesApi:
  def __init__(self, output_text: str):
    self.output_text = output_text

  def create(self, **kwargs):
    return FakeResponse(self.output_text)


class FakeClient:
  def __init__(self, output_text: str):
    self.responses = FakeResponsesApi(output_text)


class FailingResponsesApi:
  def create(self, **kwargs):
    raise RuntimeError("network down")


class FailingClient:
  def __init__(self, **kwargs):
    self.responses = FailingResponsesApi()


class AlwaysDocsClient:
  def __init__(self, **kwargs):
    self.responses = FakeResponsesApi(
      '{"classifier_id": "v_doc_writing_done", "is_match": true, "version": "v1", "milestone_id": null, "reason": "docs done"}'
    )


def build_sse_response(text: str) -> str:
  return (
    "event: response.created\n"
    'data: {"type":"response.created"}\n'
    "event: response.output_text.delta\n"
    f'data: {json.dumps({"type": "response.output_text.delta", "delta": text[:10]})}\n'
    "event: response.output_text.done\n"
    f'data: {json.dumps({"type": "response.output_text.done", "text": text})}\n'
    "event: response.completed\n"
    'data: {"type":"response.completed"}\n'
  )


def test_load_settings_reads_env_file(tmp_path: Path):
  from hooks.stop_v_task_classifier import load_settings

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )

  settings = load_settings(env_file)

  assert settings["api_key"] == "test-key"
  assert settings["base_url"] == "https://example.com/v1"
  assert settings["model"] == "gpt-test"


def test_runtime_dependencies_clear_none_openai_module_before_import():
  import hooks.stop_v_task_classifier as hook

  missing = object()
  original_openai_module = sys.modules.get("openai", missing)
  sys.modules["openai"] = None
  try:
    dotenv_values_func, openai_class = hook.load_runtime_dependencies()

    assert callable(dotenv_values_func)
    assert openai_class.__name__ == "OpenAI"
    assert sys.modules.get("openai") is not None
  finally:
    if original_openai_module is missing:
      sys.modules.pop("openai", None)
    else:
      sys.modules["openai"] = original_openai_module


def test_load_settings_normalizes_base_url_without_v1(tmp_path: Path):
  from hooks.stop_v_task_classifier import load_settings

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://www.right.codes/codex\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )

  settings = load_settings(env_file)

  assert settings["base_url"] == "https://www.right.codes/codex/v1"


def test_load_settings_normalizes_responses_preview_url(tmp_path: Path):
  from hooks.stop_v_task_classifier import load_settings

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://www.right.codes/codex/v1/responses\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )

  settings = load_settings(env_file)

  assert settings["base_url"] == "https://www.right.codes/codex/v1"


def test_classifier_definitions_include_full_v_done():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS

  assert "v_task_fully_done" in CLASSIFIER_DEFINITIONS


def test_full_v_prompt_rejects_remaining_tail_work():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS

  prompt = CLASSIFIER_DEFINITIONS["v_task_fully_done"]["prompt"].lower()

  assert "live smoke" in prompt
  assert "push" in prompt
  assert "merge" in prompt
  assert "return false" in prompt


def test_classify_last_message_parses_json():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS, classify_last_message

  client = FakeClient(
    '{"classifier_id": "v_task_fully_done", "is_match": true, "version": "v1", "milestone_id": null, "reason": "full v done"}'
  )

  result = classify_last_message(
    client,
    {"model": "gpt-test"},
    CLASSIFIER_DEFINITIONS["v_task_fully_done"],
    "v1 已全部完成",
  )

  assert result["classifier_id"] == "v_task_fully_done"
  assert result["is_match"] is True


def test_classify_last_message_parses_sse_string_response():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS, classify_last_message

  client = FakeClient(
    build_sse_response(
      '{"classifier_id": "v_task_fully_done", "is_match": true, "version": "v1", "milestone_id": null, "reason": "full v done"}'
    )
  )

  result = classify_last_message(
    client,
    {"model": "gpt-test"},
    CLASSIFIER_DEFINITIONS["v_task_fully_done"],
    "v1 已全部完成",
  )

  assert result["classifier_id"] == "v_task_fully_done"
  assert result["is_match"] is True


def test_run_hook_writes_failure_log_for_exit_one(tmp_path: Path):
  from hooks.stop_v_task_classifier import run_hook

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )
  stderr = io.StringIO()

  output, exit_code = run_hook(
    {
      "hook_event_name": "Stop",
      "last_assistant_message": "文档已经写完了。",
    },
    env_path=env_file,
    script_path=tmp_path / "stop_v_task_classifier.py",
    client_factory=FailingClient,
    stderr=stderr,
  )

  assert output is None
  assert exit_code == 1
  assert "Stop hook failed. See" in stderr.getvalue()

  log_path = tmp_path / "stop_v_task_classifier.log"
  log_content = log_path.read_text(encoding="utf-8")
  assert '"event": "hook_start"' in log_content
  assert '"event": "hook_failure"' in log_content
  assert "network down" in log_content
  assert "RuntimeError" in log_content
  assert "test-key" not in log_content
  assert "文档已经写完了。" not in log_content


def test_run_hook_does_not_fail_when_log_write_fails(tmp_path: Path, monkeypatch):
  import hooks.stop_v_task_classifier as hook

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )
  stderr = io.StringIO()

  def broken_append_log_event(*args, **kwargs):
    raise OSError("disk full")

  monkeypatch.setattr(hook, "append_log_event", broken_append_log_event)

  output, exit_code = hook.run_hook(
    {
      "hook_event_name": "Stop",
      "last_assistant_message": "文档已经写完了。",
    },
    env_path=env_file,
    script_path=tmp_path / "stop_v_task_classifier.py",
    client_factory=AlwaysDocsClient,
    stderr=stderr,
  )

  assert exit_code == 0
  assert output == {
    "continue": True,
    "decision": "block",
    "reason": hook.DOCS_REVIEW_CONTINUATION_PROMPT,
  }
  assert "Stop hook logging failed." in stderr.getvalue()
  assert "disk full" in stderr.getvalue()


def test_run_hook_skips_docs_continuation_when_payload_stop_hook_active(tmp_path: Path):
  from hooks.stop_v_task_classifier import run_hook

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )
  stderr = io.StringIO()

  output, exit_code = run_hook(
    {
      "hook_event_name": "Stop",
      "last_assistant_message": "文档已经写完了。",
      "stop_hook_active": True,
    },
    env_path=env_file,
    script_path=tmp_path / "stop_v_task_classifier.py",
    client_factory=AlwaysDocsClient,
    stderr=stderr,
  )

  assert exit_code == 0
  assert output == {"continue": True}


def test_main_logs_payload_parse_failure(tmp_path: Path, monkeypatch):
  import hooks.stop_v_task_classifier as hook

  stderr = io.StringIO()
  stdout = io.StringIO()

  monkeypatch.setattr(hook, "__file__", str(tmp_path / "stop_v_task_classifier.py"), raising=False)
  monkeypatch.setattr(hook.sys, "stdin", io.StringIO("{"))
  monkeypatch.setattr(hook.sys, "stdout", stdout)
  monkeypatch.setattr(hook.sys, "stderr", stderr)

  exit_code = hook.main()

  assert exit_code == 1
  assert stdout.getvalue() == ""
  assert "Stop hook failed. See" in stderr.getvalue()

  log_content = (tmp_path / "stop_v_task_classifier.log").read_text(encoding="utf-8")
  assert '"event": "payload_parse_failure"' in log_content
  assert "JSONDecodeError" in log_content


def test_script_logs_bootstrap_import_failure_when_openai_import_raises(tmp_path: Path):
  script_path = tmp_path / "stop_v_task_classifier.py"
  script_path.write_text(
    Path("hooks/stop_v_task_classifier.py").read_text(encoding="utf-8"),
    encoding="utf-8",
  )
  payload = json.dumps(
    {
      "hook_event_name": "Stop",
      "last_assistant_message": "v1 已完成。",
    },
    ensure_ascii=False,
  )
  (tmp_path / "openai.py").write_text(
    "raise ModuleNotFoundError('forced openai import failure')\n",
    encoding="utf-8",
  )
  runner_path = tmp_path / "runner.py"
  runner_path.write_text(
    "\n".join(
      [
        "import io",
        "import runpy",
        "import sys",
        "",
        f"sys.stdin = io.StringIO({payload!r})",
        f"runpy.run_path(r'{script_path}', run_name='__main__')",
      ]
    )
    + "\n",
    encoding="utf-8",
  )

  result = subprocess.run(
    [sys.executable, str(runner_path)],
    capture_output=True,
    text=True,
    encoding="utf-8",
  )

  assert result.returncode == 1
  assert result.stdout == ""
  assert "Stop hook failed. See" in result.stderr

  log_content = (tmp_path / "stop_v_task_classifier.log").read_text(encoding="utf-8")
  assert '"event": "hook_failure"' in log_content
  assert "ModuleNotFoundError" in log_content
  assert "forced openai import failure" in log_content


def test_full_v_priority_wins_when_multiple_match():
  from hooks.stop_v_task_classifier import build_hook_output

  output = build_hook_output([
    {
      "classifier_id": "v_doc_writing_done",
      "is_match": True,
      "version": "v1",
      "milestone_id": "M1",
      "reason": "docs",
    },
    {
      "classifier_id": "v_milestone_done",
      "is_match": True,
      "version": "v1",
      "milestone_id": "M3",
      "reason": "M3 done",
    },
    {
      "classifier_id": "v_task_fully_done",
      "is_match": True,
      "version": "v1",
      "milestone_id": None,
      "reason": "all done",
    },
  ])

  assert output == {
    "continue": True,
    "systemMessage": "hello World from hooks, on stop event, and v task has done",
  }
