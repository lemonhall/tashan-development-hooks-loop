from __future__ import annotations

from typing import Any


BRANCH_MESSAGES = {
  "v_doc_writing_done": "hello World from hooks, on stop event, and v docs have done",
  "v_milestone_done": "hello World from hooks, on stop event, and v milestone has done",
  "v_task_fully_done": "hello World from hooks, on stop event, and v task has done",
}

CLASSIFIER_DEFINITIONS = {
  "v_doc_writing_done": {
    "prompt": """You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that the documentation-writing phase for a v-series task has been completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_doc_writing_done.
Return true only when the message clearly states the docs were written, saved, or landed, often with concrete artifacts such as PRD, plan, spec, or file paths.
Also return true when the message clearly says the docs were revised, written back, updated into specific files, or changed documents are already landed, even if implementation is described as the next step.
You may infer version from explicit versioned document file names or paths such as v1-index.md or v25-*.md.
If the message is only planning, drafting, or asking for review before docs are written, return false.""",
  },
  "v_milestone_done": {
    "prompt": """You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that one milestone M inside a v-series task has been completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_milestone_done.
Return true when the message clearly states M1, M2, M3, or another milestone inside vN is complete, even if the full vN is not complete.
Return false if the message only lists milestone names, describes milestone planning, or says implementation will proceed by milestones without explicitly saying one milestone has already completed.
Return false if the message only says work is in progress or does not identify a completed milestone.""",
  },
}

CLASSIFIER_PRIORITY = [
  "v_task_fully_done",
  "v_milestone_done",
  "v_doc_writing_done",
]


def extract_last_assistant_message(payload: dict[str, Any]) -> str:
  message = payload.get("last_assistant_message")
  if not isinstance(message, str) or not message.strip():
    raise RuntimeError("Stop payload missing last_assistant_message")
  return message


def build_hook_output(classifications: list[dict[str, Any]]) -> dict[str, Any]:
  matches = {
    item.get("classifier_id"): item
    for item in classifications
    if item.get("is_match") is True
  }
  for classifier_id in CLASSIFIER_PRIORITY:
    if classifier_id in matches:
      return {"continue": True, "systemMessage": BRANCH_MESSAGES[classifier_id]}
  return {"continue": True}
