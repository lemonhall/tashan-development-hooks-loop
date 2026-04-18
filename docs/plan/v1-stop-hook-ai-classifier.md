# Stop Hook AI Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `Codex Stop hook` 中读取 `last_assistant_message`，用 Python `openai` SDK 调 `Responses API` 做三分支二次 AI 分类，并分别处理文档完成、单个 `M` 完成、整个 `v` 完成。

**Architecture:** 一个 Python hook 入口负责 stdin payload、同级 `.env`、classifier registry、Responses API 调用、分支优先级聚合与 hook JSON 输出。`v1` 拆成 `M1/M2/M3` 三个里程碑，用开发过程自然产出三类 stop 样本。

**Tech Stack:** Python 3.13、`openai` Python SDK、`python-dotenv`、`pytest`、Codex `Stop` hook JSON stdin

---

## PRD Trace

- `REQ-0001-001`：Stop payload 读取最终回复
- `REQ-0001-002`：使用 Python openai SDK 调用 Responses API
- `REQ-0001-003`：分类提示词只输出严格 JSON
- `REQ-0001-004`：`v1` 必须支持多个分类目标
- `REQ-0001-005`：`v_milestone_done` 必须识别单个 M 完成
- `REQ-0001-006`：整体 `v` 完成判定必须区分“单个 M 完成”和“整个 v 完成”
- `REQ-0001-007`：命中完成判定时返回分支提示语
- `REQ-0001-008`：从脚本同级 `.env` 读取 AI 配置
- `REQ-0001-009`：仓库必须忽略真实 `.env`
- `REQ-0001-010`：仓库必须提供 `.env.example`

## Scope

- 建立最小 Python 项目骨架
- 创建 `.gitignore` 和 `hooks/.env.example`
- 创建 `hooks/stop_v_task_classifier.py`
- 实现三类 classifier：
  - `v_doc_writing_done`
  - `v_milestone_done`
  - `v_task_fully_done`
- 实现分支输出优先级：
  - `v_task_fully_done`
  - `v_milestone_done`
  - `v_doc_writing_done`
- 创建四类 fixture：
  - 文档完成
  - 单个 M 完成
  - 整个 v 完成
  - 仍在进行中

## Non-Goals

- 不做 continuation 自动注入用户提示词
- 不做 transcript tail 读取
- 不提交真实 API 凭证
- 不做 Windows 兼容性补丁

## Branch Messages

- `v_doc_writing_done`:
  `hello World from hooks, on stop event, and v docs have done`
- `v_milestone_done`:
  `hello World from hooks, on stop event, and v milestone has done`
- `v_task_fully_done`:
  `hello World from hooks, on stop event, and v task has done`

## Files

- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `hooks/.env.example`
- Create: `hooks/stop_v_task_classifier.py`
- Create: `tests/fixtures/stop_payload_doc_done.json`
- Create: `tests/fixtures/stop_payload_milestone_done.json`
- Create: `tests/fixtures/stop_payload_v_task_done.json`
- Create: `tests/fixtures/stop_payload_not_done.json`
- Create: `tests/test_stop_v_task_classifier.py`

## M1: 文档完成分支

**Goal:** 建立项目骨架、secrets 边界和 `v_doc_writing_done`，先让“文档写作完成”样本跑通。

**Files:**

- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `hooks/.env.example`
- Create: `hooks/stop_v_task_classifier.py`
- Create: `tests/fixtures/stop_payload_doc_done.json`
- Create: `tests/fixtures/stop_payload_not_done.json`
- Create: `tests/test_stop_v_task_classifier.py`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path

from hooks.stop_v_task_classifier import build_hook_output, extract_last_assistant_message


def test_gitignore_ignores_real_env():
    content = Path(".gitignore").read_text(encoding="utf-8")
    assert "hooks/.env" in content


def test_env_example_contains_required_keys():
    content = Path("hooks/.env.example").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" in content
    assert "OPENAI_BASE_URL=" in content
    assert "OPENAI_MODEL=" in content


def test_extract_last_assistant_message_returns_string():
    payload = {
        "hook_event_name": "Stop",
        "last_assistant_message": "文档已经写到目标目录了，PRD、v1-index 和 v1 计划都已经落盘。",
    }
    assert extract_last_assistant_message(payload) == "文档已经写到目标目录了，PRD、v1-index 和 v1 计划都已经落盘。"


def test_build_hook_output_returns_docs_message_for_doc_done():
    output = build_hook_output([
        {"classifier_id": "v_doc_writing_done", "is_match": True, "version": "v1", "milestone_id": "M1", "reason": "docs saved"},
    ])
    assert output == {
        "continue": True,
        "systemMessage": "hello World from hooks, on stop event, and v docs have done",
    }
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示项目文件或 `hooks.stop_v_task_classifier` 不存在。

- [ ] **Step 3: 写最小实现**

`.gitignore`

```gitignore
.venv/
__pycache__/
.pytest_cache/
hooks/.env
```

`pyproject.toml`

```toml
[project]
name = "tashan-development-hooks-loop"
version = "0.1.0"
description = "Codex stop hook v-task classifier"
requires-python = ">=3.13"
dependencies = [
  "openai",
  "python-dotenv",
]

[dependency-groups]
dev = [
  "pytest",
]
```

`hooks/.env.example`

```dotenv
OPENAI_API_KEY=replace-me
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-mini
```

`hooks/stop_v_task_classifier.py`

```python
from __future__ import annotations

from typing import Any

BRANCH_MESSAGES = {
    "v_doc_writing_done": "hello World from hooks, on stop event, and v docs have done",
    "v_milestone_done": "hello World from hooks, on stop event, and v milestone has done",
    "v_task_fully_done": "hello World from hooks, on stop event, and v task has done",
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
```

`tests/fixtures/stop_payload_doc_done.json`

```json
{
  "hook_event_name": "Stop",
  "last_assistant_message": "文档已经写到目标目录了，PRD、v1-index 和 v1 计划都已经落盘。"
}
```

`tests/fixtures/stop_payload_not_done.json`

```json
{
  "hook_event_name": "Stop",
  "last_assistant_message": "目前已完成分析，下一步还需要继续实现和验证。"
}
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add -A ; git commit -m "v1: feat: M1 doc completion classifier"
```

## M2: 单个里程碑完成分支

**Goal:** 增加 `v_milestone_done`，让“某个 M 完成但整个 v 未完成”成为独立可处理分支。

**Files:**

- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `tests/test_stop_v_task_classifier.py`
- Create: `tests/fixtures/stop_payload_milestone_done.json`

- [ ] **Step 1: 写失败测试**

```python
from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS, build_hook_output


def test_classifier_definitions_include_milestone_done():
    assert "v_milestone_done" in CLASSIFIER_DEFINITIONS


def test_build_hook_output_returns_milestone_message_for_m_done():
    output = build_hook_output([
        {"classifier_id": "v_doc_writing_done", "is_match": False, "version": "v1", "milestone_id": "M2", "reason": "not docs"},
        {"classifier_id": "v_milestone_done", "is_match": True, "version": "v1", "milestone_id": "M2", "reason": "M2 complete"},
        {"classifier_id": "v_task_fully_done", "is_match": False, "version": "v1", "milestone_id": "M2", "reason": "v1 still has M3"},
    ])
    assert output == {
        "continue": True,
        "systemMessage": "hello World from hooks, on stop event, and v milestone has done",
    }
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `CLASSIFIER_DEFINITIONS` 不存在或缺少 `v_milestone_done`。

- [ ] **Step 3: 加入 milestone classifier prompt**

在 `hooks/stop_v_task_classifier.py` 中加入：

```python
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
```

`tests/fixtures/stop_payload_milestone_done.json`

```json
{
  "hook_event_name": "Stop",
  "last_assistant_message": "M2 已完成，单个里程碑的分类器、fixture 和测试都已经落盘；v1 还剩 M3。"
}
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add -A ; git commit -m "v1: feat: M2 milestone completion classifier"
```

## M3: 整体 v 完成分支

**Goal:** 增加 `v_task_fully_done`、Responses API 调用、`.env` 读取和最终 smoke，使三分支闭环完整。

**Files:**

- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `tests/test_stop_v_task_classifier.py`
- Create: `tests/fixtures/stop_payload_v_task_done.json`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path

from hooks.stop_v_task_classifier import CLASSIFIER_DEFINITIONS, classify_last_message, load_settings, build_hook_output


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


def test_load_settings_reads_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file)
    assert settings["api_key"] == "test-key"
    assert settings["base_url"] == "https://example.com/v1"
    assert settings["model"] == "gpt-test"


def test_classifier_definitions_include_full_v_done():
    assert "v_task_fully_done" in CLASSIFIER_DEFINITIONS


def test_classify_last_message_parses_json():
    client = FakeClient('{"classifier_id": "v_task_fully_done", "is_match": true, "version": "v1", "milestone_id": null, "reason": "full v done"}')
    result = classify_last_message(client, {"model": "gpt-test"}, CLASSIFIER_DEFINITIONS["v_task_fully_done"], "v1 已全部完成")
    assert result["classifier_id"] == "v_task_fully_done"
    assert result["is_match"] is True


def test_full_v_priority_wins_when_multiple_match():
    output = build_hook_output([
        {"classifier_id": "v_doc_writing_done", "is_match": True, "version": "v1", "milestone_id": "M1", "reason": "docs"},
        {"classifier_id": "v_milestone_done", "is_match": True, "version": "v1", "milestone_id": "M3", "reason": "M3 done"},
        {"classifier_id": "v_task_fully_done", "is_match": True, "version": "v1", "milestone_id": None, "reason": "all done"},
    ])
    assert output == {
        "continue": True,
        "systemMessage": "hello World from hooks, on stop event, and v task has done",
    }
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `load_settings` / `classify_last_message` 未定义或缺少 `v_task_fully_done`。

- [ ] **Step 3: 实现 `.env`、Responses API 与 full-v classifier**

在 `hooks/stop_v_task_classifier.py` 中补齐：

```python
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

CLASSIFIER_DEFINITIONS["v_task_fully_done"] = {
    "prompt": """You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that an entire v-series task has been fully completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_task_fully_done.
Return true only if the message clearly indicates the whole vN scope is complete.
If the message only says one milestone M is done, part of the code is done, docs are done, or more implementation/testing/verification remains, return false.""",
}


def load_settings(env_path: Path) -> dict[str, str]:
    values = dotenv_values(env_path)
    api_key = values.get("OPENAI_API_KEY")
    base_url = values.get("OPENAI_BASE_URL")
    model = values.get("OPENAI_MODEL")
    missing = [name for name, value in {
        "OPENAI_API_KEY": api_key,
        "OPENAI_BASE_URL": base_url,
        "OPENAI_MODEL": model,
    }.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
    return {"api_key": api_key, "base_url": base_url, "model": model}


def classify_last_message(client: OpenAI, settings: dict[str, str], classifier_definition: dict[str, str], message: str) -> dict[str, Any]:
    response = client.responses.create(
        model=settings["model"],
        input=[
            {"role": "system", "content": classifier_definition["prompt"]},
            {"role": "user", "content": message},
        ],
    )
    result = json.loads(response.output_text)
    if "classifier_id" not in result or "is_match" not in result:
        raise RuntimeError("Classifier JSON missing classifier_id or is_match")
    return result


def main() -> int:
    payload = json.load(sys.stdin)
    message = extract_last_assistant_message(payload)
    env_path = Path(__file__).with_name(".env")
    settings = load_settings(env_path)
    client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"])
    classifications = [
        classify_last_message(client, settings, classifier_definition, message)
        for classifier_definition in CLASSIFIER_DEFINITIONS.values()
    ]
    json.dump(build_hook_output(classifications), sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/fixtures/stop_payload_v_task_done.json`

```json
{
  "hook_event_name": "Stop",
  "last_assistant_message": "v1 已全部完成：M1 文档完成分支、M2 单个里程碑完成分支、M3 整体 v 完成分支都已实现并验证通过。"
}
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests/test_stop_v_task_classifier.py -q
```

Expected:

- PASS

- [ ] **Step 5: 手工 smoke**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_doc_done.json | uv run python hooks/stop_v_task_classifier.py
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_milestone_done.json | uv run python hooks/stop_v_task_classifier.py
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_v_task_done.json | uv run python hooks/stop_v_task_classifier.py
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_not_done.json | uv run python hooks/stop_v_task_classifier.py
```

Expected:

- doc fixture 输出 docs 分支消息
- milestone fixture 输出 milestone 分支消息
- full-v fixture 输出 task 分支消息
- not-done fixture 输出 `{"continue": true}`

- [ ] **Step 6: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add -A ; git commit -m "v1: feat: M3 full v classifier and smoke"
```

## Risks

- 官方文档截至 `2026-04-19` 仍声明 Windows hooks 暂未支持，真实联调可能受运行时限制影响。
- 只使用 `last_assistant_message` 做分类输入，语义模糊时仍可能误判。
- “单个 `M` 完成”和“整个 `v` 完成”的边界需要通过 `M1/M2/M3` 的真实 stop 样本继续校准。

## Review Checklist

- [ ] `.gitignore` 忽略真实 `.env`
- [ ] `hooks/.env.example` 只包含占位符
- [ ] `v_doc_writing_done`、`v_milestone_done`、`v_task_fully_done` 三分支都存在
- [ ] 输出优先级为 `v_task_fully_done > v_milestone_done > v_doc_writing_done`
- [ ] 测试覆盖文档完成、单个 M 完成、整个 v 完成、仍在进行中、缺失配置
- [ ] 输出 JSON 无 markdown 包裹
- [ ] 未把 continuation 注入偷带进 `v1`
