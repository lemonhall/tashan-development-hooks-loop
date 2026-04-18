from pathlib import Path


def test_gitignore_ignores_real_env():
  content = Path(".gitignore").read_text(encoding="utf-8")
  assert "hooks/.env" in content


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


def test_build_hook_output_returns_docs_message_for_doc_done():
  from hooks.stop_v_task_classifier import build_hook_output

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
    "systemMessage": "hello World from hooks, on stop event, and v docs have done",
  }


def test_classifier_definitions_include_milestone_done():
  from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS

  assert "v_milestone_done" in CLASSIFIER_DEFINITIONS


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
