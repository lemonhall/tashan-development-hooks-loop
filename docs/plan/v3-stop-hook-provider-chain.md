# v3 Stop Hook Provider Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `Stop` hook 在多供应商、多 wire API 之间按显式顺序自动 fallback，并在 `gpt-5.4` 的 `/responses` 不兼容场景下仍能完成三类 classifier 判定。

**Architecture:** 保留现有三类 classifier、优先级与 docs 分支 continuation 输出，只把“调用模型并提取 classifier JSON”重构为 `provider chain + transport layer`。配置层从 `.env` 读取 `HOOK_PROVIDER_N_*` 编号 provider；运行时先在 provider 内按 `WIRE_APIS` 顺序尝试 `responses` 与 `chat_completions_stream`，再在 provider 之间做主备 failover；每次 attempt 都写结构化日志，全部失败时输出聚合错误。

**Tech Stack:** Python 3.13+、`openai` Python SDK、`python-dotenv`、`httpx`、`pytest`、Codex `Stop` hook JSON stdin

---

## PRD Trace

- `REQ-0001-002`：使用 Python openai SDK 调用 Responses API
- `REQ-0001-008`：从脚本同级 `.env` 读取 AI 配置
- `REQ-0001-009`：仓库必须忽略真实 `.env`
- `REQ-0001-010`：仓库必须提供 `.env.example`
- `INFRA-provider-chain`：多 provider 主备链、协议 fallback、attempt 级诊断

## Scope

- 保留现有三类 classifier、优先级与 docs 分支 continuation 输出
- 新增编号 provider chain 配置解析
- 保留 legacy `OPENAI_*` 单 provider 兼容模式
- 新增 `responses` transport 与 `chat_completions_stream` transport
- 新增 provider 内协议 fallback
- 新增 provider 间主备 failover
- 新增 attempt 级日志与聚合失败摘要
- 同步 `.env.example`、README、AGENTS、PRD、spec
- 完成本地与全局 docs fixture smoke

## Non-Goals

- 不新增 classifier
- 不修改 docs review continuation prompt 文案
- 不做 session 级防重入 / 防循环状态机
- 不做无限重试
- 不写 provider-specific 硬编码域名分支

## Acceptance

1. `.env` 支持 `HOOK_PROVIDER_1_*`, `HOOK_PROVIDER_2_*` 编号 provider 配置；不存在链式配置时仍兼容旧 `OPENAI_*`。
2. 当 provider 的 `/responses` 返回空 body、非 JSON、非预期 SSE、网络错误、超时、5xx，或明确协议不兼容 / 配置不兼容错误时，hook 会尝试该 provider 的下一个 `WIRE_API`。
3. 当当前 provider 的 `WIRE_APIS` 全部失败时，hook 会切到下一个 provider。
4. `chat_completions_stream` 能从 SSE 的 `choices[0].delta.content` 正确拼出最终文本。
5. 全部 provider 都失败时，最终错误与日志中都能看到每次 attempt 的摘要。
6. `uv run pytest -q` 全绿；本地 docs fixture smoke 通过；全局 hook docs fixture smoke 通过。

## File Structure

- Modify: `pyproject.toml`
  - 新增 `httpx` 依赖，供 `chat_completions_stream` transport 使用。
- Modify: `hooks/.env.example`
  - 同时展示 legacy `OPENAI_*` 与 `HOOK_PROVIDER_N_*` 链式配置。
- Modify: `hooks/stop_v_task_classifier.py`
  - 新增 provider config、transport、attempt 日志、provider chain orchestration。
- Modify: `tests/test_stop_v_task_classifier.py`
  - 覆盖配置解析、stream transport、provider failover、聚合失败与日志事件。
- Modify: `README.md`
  - 说明 provider chain `.env` 写法、fallback 规则、验证命令。
- Modify: `AGENTS.md`
  - 固化 provider chain 安装/验证约束与日志约束。
- Modify: `docs/prd/PRD-0001-stop-hook-v-task-classifier.md`
  - 补充 v3 的 transport compatibility 要求与验收。
- Modify: `docs/superpowers/specs/2026-04-19-stop-hook-provider-chain-design.md`
  - 保持实施细节与最终实现一致。

### Task 1: Provider Chain 配置层

**Files:**
- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `hooks/.env.example`
- Modify: `tests/test_stop_v_task_classifier.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 写失败测试**

```python
def test_env_example_documents_provider_chain_keys():
  content = Path("hooks/.env.example").read_text(encoding="utf-8")
  assert "HOOK_PROVIDER_1_NAME=" in content
  assert "HOOK_PROVIDER_1_WIRE_APIS=" in content


def test_load_provider_chain_settings_reads_numbered_providers(tmp_path: Path):
  from hooks.stop_v_task_classifier import load_provider_chain_settings

  env_file = tmp_path / ".env"
  env_file.write_text(
    "\n".join(
      [
        "HOOK_PROVIDER_1_NAME=primary",
        "HOOK_PROVIDER_1_BASE_URL=https://api-vip.codex-for.me/v1",
        "HOOK_PROVIDER_1_API_KEY=primary-key",
        "HOOK_PROVIDER_1_MODEL=gpt-5.4",
        "HOOK_PROVIDER_1_WIRE_APIS=responses,chat_completions_stream",
        "HOOK_PROVIDER_2_NAME=backup",
        "HOOK_PROVIDER_2_BASE_URL=https://www.right.codes/codex",
        "HOOK_PROVIDER_2_API_KEY=backup-key",
        "HOOK_PROVIDER_2_MODEL=gpt-5.4-high",
        "HOOK_PROVIDER_2_WIRE_APIS=responses",
      ]
    )
    + "\n",
    encoding="utf-8",
  )

  providers = load_provider_chain_settings(env_file)

  assert [provider.name for provider in providers] == ["primary", "backup"]
  assert providers[0].wire_apis == ("responses", "chat_completions_stream")
  assert providers[1].base_url == "https://www.right.codes/codex/v1"


def test_load_provider_chain_settings_falls_back_to_legacy_openai_keys(tmp_path: Path):
  from hooks.stop_v_task_classifier import load_provider_chain_settings

  env_file = tmp_path / ".env"
  env_file.write_text(
    "OPENAI_API_KEY=test-key\nOPENAI_BASE_URL=https://example.com/v1\nOPENAI_MODEL=gpt-test\n",
    encoding="utf-8",
  )

  providers = load_provider_chain_settings(env_file)

  assert len(providers) == 1
  assert providers[0].name == "default"
  assert providers[0].wire_apis == ("responses",)
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `load_provider_chain_settings` 不存在，且 `.env.example` 缺少 `HOOK_PROVIDER_1_*` 键。

- [ ] **Step 3: 写最小实现**

`pyproject.toml`

```toml
[project]
dependencies = [
  "openai",
  "python-dotenv",
  "httpx",
]
```

`hooks/.env.example`

```dotenv
OPENAI_API_KEY=replace-me
# Accepts provider root, /v1 base, or a pasted /v1/responses preview URL.
# The hook normalizes this to a Responses API-compatible /v1 base URL.
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-mini

# Optional provider chain. If HOOK_PROVIDER_1_* exists, the hook uses it first.
HOOK_PROVIDER_1_NAME=primary
HOOK_PROVIDER_1_BASE_URL=https://api-vip.codex-for.me/v1
HOOK_PROVIDER_1_API_KEY=replace-me
HOOK_PROVIDER_1_MODEL=gpt-5.4
HOOK_PROVIDER_1_WIRE_APIS=responses,chat_completions_stream

HOOK_PROVIDER_2_NAME=backup
HOOK_PROVIDER_2_BASE_URL=https://www.right.codes/codex/v1
HOOK_PROVIDER_2_API_KEY=replace-me
HOOK_PROVIDER_2_MODEL=gpt-5.4-high
HOOK_PROVIDER_2_WIRE_APIS=responses
```

`hooks/stop_v_task_classifier.py`

```python
from dataclasses import dataclass

SUPPORTED_WIRE_APIS = ("responses", "chat_completions_stream")


@dataclass(frozen=True)
class ProviderConfig:
  name: str
  api_key: str
  base_url: str
  model: str
  wire_apis: tuple[str, ...]


def parse_wire_apis(raw_value: str) -> tuple[str, ...]:
  wire_apis = tuple(item.strip() for item in raw_value.split(",") if item.strip())
  if not wire_apis:
    raise RuntimeError("Provider config must declare at least one wire api")
  invalid = [item for item in wire_apis if item not in SUPPORTED_WIRE_APIS]
  if invalid:
    raise RuntimeError(f"Unsupported wire apis: {', '.join(invalid)}")
  return wire_apis


def build_legacy_provider(values: dict[str, Any]) -> ProviderConfig:
  api_key = values.get("OPENAI_API_KEY")
  base_url = values.get("OPENAI_BASE_URL")
  model = values.get("OPENAI_MODEL")
  missing = [
    name
    for name, value in {
      "OPENAI_API_KEY": api_key,
      "OPENAI_BASE_URL": base_url,
      "OPENAI_MODEL": model,
    }.items()
    if not value
  ]
  if missing:
    raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
  return ProviderConfig(
    name="default",
    api_key=str(api_key),
    base_url=normalize_base_url(str(base_url)),
    model=str(model),
    wire_apis=("responses",),
  )


def load_provider_chain_settings(
  env_path: Path,
  *,
  dotenv_values_func: Any | None = None,
) -> list[ProviderConfig]:
  if dotenv_values_func is None:
    dotenv_values_func, _ = load_runtime_dependencies()
  values = dotenv_values_func(env_path)

  if not values.get("HOOK_PROVIDER_1_BASE_URL"):
    return [build_legacy_provider(values)]

  providers: list[ProviderConfig] = []
  index = 1
  while values.get(f"HOOK_PROVIDER_{index}_BASE_URL"):
    prefix = f"HOOK_PROVIDER_{index}_"
    name = values.get(f"{prefix}NAME") or f"provider_{index}"
    api_key = values.get(f"{prefix}API_KEY")
    base_url = values.get(f"{prefix}BASE_URL")
    model = values.get(f"{prefix}MODEL")
    wire_apis = values.get(f"{prefix}WIRE_APIS")
    missing = [
      field
      for field, value in {
        "API_KEY": api_key,
        "BASE_URL": base_url,
        "MODEL": model,
        "WIRE_APIS": wire_apis,
      }.items()
      if not value
    ]
    if missing:
      raise RuntimeError(f"Provider {index} missing fields: {', '.join(missing)}")
    providers.append(
      ProviderConfig(
        name=str(name),
        api_key=str(api_key),
        base_url=normalize_base_url(str(base_url)),
        model=str(model),
        wire_apis=parse_wire_apis(str(wire_apis)),
      )
    )
    index += 1
  return providers
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- PASS，新增配置解析测试通过。

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add pyproject.toml hooks/.env.example hooks/stop_v_task_classifier.py tests/test_stop_v_task_classifier.py ; git commit -m "v3: feat: add provider chain config parsing"
```

### Task 2: 拆分 classifier 解析与 `responses` transport

**Files:**
- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `tests/test_stop_v_task_classifier.py`

- [ ] **Step 1: 写失败测试**

```python
def test_parse_classifier_response_text_rejects_empty_body():
  from hooks.stop_v_task_classifier import parse_classifier_response_text

  try:
    parse_classifier_response_text("", source="responses")
  except RuntimeError as exc:
    assert "empty response body" in str(exc).lower()
    assert "/responses" in str(exc)
  else:
    raise AssertionError("Expected RuntimeError for empty body")


def test_run_provider_attempt_uses_responses_transport():
  from hooks.stop_v_task_classifier import ProviderConfig, run_provider_attempt

  provider = ProviderConfig(
    name="primary",
    api_key="test-key",
    base_url="https://example.com/v1",
    model="gpt-test",
    wire_apis=("responses",),
  )

  success = run_provider_attempt(
    provider,
    "responses",
    {"prompt": "Return JSON"},
    "done",
    openai_client_factory=lambda **kwargs: FakeClient(
      '{"classifier_id":"v_doc_writing_done","is_match":true,"version":"v1","milestone_id":null,"reason":"ok"}'
    ),
    chat_stream_requester=None,
  )

  assert success.provider_name == "primary"
  assert success.wire_api == "responses"
  assert success.result["classifier_id"] == "v_doc_writing_done"
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `parse_classifier_response_text` / `run_provider_attempt` 未定义。

- [ ] **Step 3: 写最小实现**

`hooks/stop_v_task_classifier.py`

```python
@dataclass(frozen=True)
class ProviderAttemptSuccess:
  provider_name: str
  wire_api: str
  text_length: int
  result: dict[str, Any]


def parse_classifier_response_text(raw_text: str, *, source: str) -> dict[str, Any]:
  if not raw_text.strip():
    if source == "responses":
      raise RuntimeError(
        "Responses API returned an empty response body for /responses; "
        "provider may not support the endpoint correctly"
      )
    raise RuntimeError(f"{source} returned an empty response body")
  try:
    result = json.loads(raw_text)
  except json.JSONDecodeError as exc:
    preview = raw_text[:200].replace("\r", "\\r").replace("\n", "\\n")
    raise RuntimeError(
      f"{source} returned non-JSON output for classifier parsing. preview={preview!r}"
    ) from exc
  if "classifier_id" not in result or "is_match" not in result:
    raise RuntimeError("Classifier JSON missing classifier_id or is_match")
  return result


def run_provider_attempt(
  provider: ProviderConfig,
  wire_api: str,
  classifier_definition: dict[str, str],
  message: str,
  *,
  openai_client_factory: Any,
  chat_stream_requester: Any | None,
) -> ProviderAttemptSuccess:
  if wire_api != "responses":
    raise RuntimeError(f"Unsupported wire api in Task 2: {wire_api}")
  client = openai_client_factory(api_key=provider.api_key, base_url=provider.base_url)
  response = client.responses.create(
    model=provider.model,
    input=[
      {"role": "system", "content": classifier_definition["prompt"]},
      {"role": "user", "content": message},
    ],
  )
  raw_text = extract_response_text(response)
  result = parse_classifier_response_text(raw_text, source="responses")
  return ProviderAttemptSuccess(
    provider_name=provider.name,
    wire_api="responses",
    text_length=len(raw_text),
    result=result,
  )
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- PASS，`responses` transport 可独立返回 classifier JSON。

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add hooks/stop_v_task_classifier.py tests/test_stop_v_task_classifier.py ; git commit -m "v3: feat: refactor classifier response parsing"
```

### Task 3: 增加 `chat_completions_stream` transport 与 provider 内协议 fallback

**Files:**
- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `tests/test_stop_v_task_classifier.py`

- [ ] **Step 1: 写失败测试**

```python
def test_extract_chat_completions_text_from_sse():
  from hooks.stop_v_task_classifier import extract_chat_completions_text_from_sse

  payload = (
    'data: {"choices":[{"delta":{"content":"{\\"ok\\":true"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"}"}}]}\n\n'
    'data: [DONE]\n\n'
  )

  assert extract_chat_completions_text_from_sse(payload) == '{"ok":true}'


def test_classify_last_message_with_provider_chain_falls_back_to_chat_stream_after_empty_responses_body():
  from hooks.stop_v_task_classifier import ProviderConfig, classify_last_message_with_provider_chain

  provider = ProviderConfig(
    name="primary",
    api_key="test-key",
    base_url="https://example.com/v1",
    model="gpt-5.4",
    wire_apis=("responses", "chat_completions_stream"),
  )

  result = classify_last_message_with_provider_chain(
    [provider],
    {"prompt": "Return JSON"},
    "done",
    openai_client_factory=lambda **kwargs: EmptyStringClient(),
    chat_stream_requester=lambda provider, prompt, message: (
      'data: {"choices":[{"delta":{"content":"{\\"classifier_id\\":\\"v_doc_writing_done\\",\\"is_match\\":true,\\"version\\":\\"v1\\",\\"milestone_id\\":null,\\"reason\\":\\"ok\\"}"}}]}\n\n'
      'data: [DONE]\n\n'
    ),
    attempt_logger=None,
  )

  assert result["classifier_id"] == "v_doc_writing_done"
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `extract_chat_completions_text_from_sse` / `classify_last_message_with_provider_chain` 未定义。

- [ ] **Step 3: 写最小实现**

`hooks/stop_v_task_classifier.py`

```python
import httpx


@dataclass(frozen=True)
class ProviderAttemptFailure:
  provider_name: str
  wire_api: str
  error_type: str
  error_message: str


def extract_chat_completions_text_from_sse(response_text: str) -> str:
  chunks: list[str] = []
  for line in response_text.splitlines():
    if not line.startswith("data: "):
      continue
    payload = line[len("data: ") :].strip()
    if not payload or payload == "[DONE]":
      continue
    item = json.loads(payload)
    choices = item.get("choices") or []
    if not choices:
      continue
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
      chunks.append(content)
  if not chunks:
    raise RuntimeError("chat_completions_stream SSE did not contain assistant content")
  return "".join(chunks)


def default_chat_stream_requester(provider: ProviderConfig, prompt: str, message: str) -> str:
  payload = {
    "model": provider.model,
    "messages": [
      {"role": "system", "content": prompt},
      {"role": "user", "content": message},
    ],
    "stream": True,
  }
  with httpx.Client(timeout=90.0) as client:
    with client.stream(
      "POST",
      f"{provider.base_url}/chat/completions",
      headers={
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
      },
      json=payload,
    ) as response:
      response.raise_for_status()
      return "".join(response.iter_text())


def classify_last_message_with_provider_chain(
  providers: list[ProviderConfig],
  classifier_definition: dict[str, str],
  message: str,
  *,
  openai_client_factory: Any,
  chat_stream_requester: Any | None,
  attempt_logger: Any | None,
) -> dict[str, Any]:
  requester = default_chat_stream_requester if chat_stream_requester is None else chat_stream_requester
  failures: list[ProviderAttemptFailure] = []

  for provider in providers:
    for wire_api in provider.wire_apis:
      if attempt_logger is not None:
        attempt_logger("attempt", provider, wire_api)
      try:
        if wire_api == "responses":
          success = run_provider_attempt(
            provider,
            wire_api,
            classifier_definition,
            message,
            openai_client_factory=openai_client_factory,
            chat_stream_requester=requester,
          )
        elif wire_api == "chat_completions_stream":
          raw_text = extract_chat_completions_text_from_sse(
            requester(provider, classifier_definition["prompt"], message)
          )
          success = ProviderAttemptSuccess(
            provider_name=provider.name,
            wire_api=wire_api,
            text_length=len(raw_text),
            result=parse_classifier_response_text(raw_text, source=wire_api),
          )
        else:
          raise RuntimeError(f"Unsupported wire api: {wire_api}")
      except Exception as exc:
        failures.append(
          ProviderAttemptFailure(
            provider_name=provider.name,
            wire_api=wire_api,
            error_type=type(exc).__name__,
            error_message=str(exc),
          )
        )
        if attempt_logger is not None:
          attempt_logger("failure", provider, wire_api, error=exc)
        continue

      if attempt_logger is not None:
        attempt_logger("success", provider, wire_api, text_length=success.text_length)
      return success.result

  if attempt_logger is not None:
    attempt_logger("chain_failure", None, None, failures=failures)
  raise RuntimeError(
    "All provider attempts failed: "
    + "; ".join(f"{item.provider_name}/{item.wire_api} -> {item.error_message}" for item in failures)
  )
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- PASS，空 body 时会自动切到 `chat_completions_stream`。

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add hooks/stop_v_task_classifier.py tests/test_stop_v_task_classifier.py pyproject.toml ; git commit -m "v3: feat: add chat completions stream fallback"
```

### Task 4: 集成到 `run_hook()` 并补齐 attempt 级日志与聚合失败

**Files:**
- Modify: `hooks/stop_v_task_classifier.py`
- Modify: `tests/test_stop_v_task_classifier.py`

- [ ] **Step 1: 写失败测试**

```python
def test_provider_chain_uses_backup_provider_after_primary_exhausted():
  from hooks.stop_v_task_classifier import ProviderConfig, classify_last_message_with_provider_chain

  providers = [
    ProviderConfig("primary", "k1", "https://p1.example/v1", "gpt-5.4", ("responses", "chat_completions_stream")),
    ProviderConfig("backup", "k2", "https://p2.example/v1", "gpt-5.4-high", ("responses",)),
  ]

  result = classify_last_message_with_provider_chain(
    providers,
    {"prompt": "Return JSON"},
    "done",
    openai_client_factory=lambda **kwargs: (
      EmptyStringClient() if "p1.example" in kwargs["base_url"] else AlwaysDocsClient()
    ),
    chat_stream_requester=lambda provider, prompt, message: (_ for _ in ()).throw(RuntimeError("stream unavailable")),
    attempt_logger=None,
  )

  assert result["reason"] == "docs done"


def test_run_hook_logs_provider_attempt_events_with_actual_success_attempt(tmp_path: Path):
  import hooks.stop_v_task_classifier as hook

  env_file = tmp_path / ".env"
  env_file.write_text(
    "\n".join(
      [
        "HOOK_PROVIDER_1_NAME=primary",
        "HOOK_PROVIDER_1_BASE_URL=https://primary.example/v1",
        "HOOK_PROVIDER_1_API_KEY=key-1",
        "HOOK_PROVIDER_1_MODEL=gpt-5.4",
        "HOOK_PROVIDER_1_WIRE_APIS=responses,chat_completions_stream",
        "HOOK_PROVIDER_2_NAME=backup",
        "HOOK_PROVIDER_2_BASE_URL=https://backup.example/v1",
        "HOOK_PROVIDER_2_API_KEY=key-2",
        "HOOK_PROVIDER_2_MODEL=gpt-5.4-high",
        "HOOK_PROVIDER_2_WIRE_APIS=responses",
      ]
    ) + "\n",
    encoding="utf-8",
  )

  output, exit_code = hook.run_hook(
    {"hook_event_name": "Stop", "last_assistant_message": "文档已经完成并落盘。"},
    env_path=env_file,
    script_path=tmp_path / "stop_v_task_classifier.py",
    client_factory=lambda **kwargs: (
      EmptyStringClient() if "primary.example" in kwargs["base_url"] else AlwaysDocsClient()
    ),
    chat_stream_requester=lambda provider, prompt, message: (_ for _ in ()).throw(RuntimeError("stream unavailable")),
    stderr=io.StringIO(),
  )

  assert exit_code == 0
  assert output["decision"] == "block"

  log_content = (tmp_path / "stop_v_task_classifier.log").read_text(encoding="utf-8")
  assert '"event": "provider_attempt"' in log_content
  assert '"event": "provider_attempt_failure"' in log_content
  assert '"event": "provider_attempt_success"' in log_content
  assert '"provider_name": "backup"' in log_content
  assert '"wire_api": "responses"' in log_content


def test_classify_last_message_with_provider_chain_raises_aggregated_error():
  from hooks.stop_v_task_classifier import ProviderConfig, classify_last_message_with_provider_chain

  providers = [
    ProviderConfig("primary", "k1", "https://p1.example/v1", "gpt-5.4", ("responses", "chat_completions_stream")),
  ]

  try:
    classify_last_message_with_provider_chain(
      providers,
      {"prompt": "Return JSON"},
      "done",
      openai_client_factory=lambda **kwargs: EmptyStringClient(),
      chat_stream_requester=lambda provider, prompt, message: (_ for _ in ()).throw(RuntimeError("stream unavailable")),
      attempt_logger=None,
    )
  except RuntimeError as exc:
    assert "primary/responses" in str(exc)
    assert "primary/chat_completions_stream" in str(exc)
  else:
    raise AssertionError("Expected aggregated provider chain failure")
```

- [ ] **Step 2: 跑红**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- FAIL，提示 `run_hook()` 还没有接入 provider chain，或日志里缺少真实成功 attempt 元数据。

- [ ] **Step 3: 写最小实现**

`hooks/stop_v_task_classifier.py`

```python
def build_attempt_logger(log_path: Path, stderr: Any):
  def _log(
    event_type: str,
    provider: ProviderConfig | None,
    wire_api: str | None,
    *,
    error: Exception | None = None,
    text_length: int | None = None,
    failures: list[ProviderAttemptFailure] | None = None,
  ) -> None:
    if event_type == "attempt" and provider is not None and wire_api is not None:
      try_append_log_event(
        log_path,
        "provider_attempt",
        stderr=stderr,
        provider_name=provider.name,
        base_url=provider.base_url,
        wire_api=wire_api,
        model=provider.model,
      )
      return
    if event_type == "failure" and provider is not None and wire_api is not None and error is not None:
      try_append_log_event(
        log_path,
        "provider_attempt_failure",
        stderr=stderr,
        provider_name=provider.name,
        wire_api=wire_api,
        error_type=type(error).__name__,
        error_message=str(error),
      )
      return
    if event_type == "success" and provider is not None and wire_api is not None:
      try_append_log_event(
        log_path,
        "provider_attempt_success",
        stderr=stderr,
        provider_name=provider.name,
        wire_api=wire_api,
        text_length=text_length,
      )
      return
    if event_type == "chain_failure" and failures is not None:
      try_append_log_event(
        log_path,
        "provider_chain_failure",
        stderr=stderr,
        attempts=[
          {
            "provider_name": item.provider_name,
            "wire_api": item.wire_api,
            "error_type": item.error_type,
            "error_message": item.error_message,
          }
          for item in failures
        ],
      )
  return _log
```

并把 `run_hook()` 改成显式加载 provider chain，而不是先构造单一 `client`：

```python
def run_hook(
  payload: Any,
  *,
  env_path: Path,
  script_path: Path,
  client_factory: Any = None,
  chat_stream_requester: Any = None,
  stderr: Any = sys.stderr,
) -> tuple[dict[str, Any] | None, int]:
  ...
  providers = load_provider_chain_settings(env_path, dotenv_values_func=dotenv_values_func)
  attempt_logger = build_attempt_logger(log_path, stderr)
  if client_factory is None:
    client_factory = openai_client_factory

  classifications: list[dict[str, Any]] = []
  for classifier_id, classifier_definition in CLASSIFIER_DEFINITIONS.items():
    result = classify_last_message_with_provider_chain(
      providers,
      classifier_definition,
      message,
      openai_client_factory=client_factory,
      chat_stream_requester=chat_stream_requester,
      attempt_logger=attempt_logger,
    )
    classifications.append(result)
    try_append_log_event(
      log_path,
      "classifier_result",
      stderr=stderr,
      classifier_id=classifier_id,
      is_match=result.get("is_match"),
      version=result.get("version"),
      milestone_id=result.get("milestone_id"),
    )
```

- [ ] **Step 4: 跑绿**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q
```

Expected:

- PASS，主备切换、聚合失败与 attempt 事件日志测试通过。

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add hooks/stop_v_task_classifier.py tests/test_stop_v_task_classifier.py ; git commit -m "v3: feat: add provider failover logging"
```

### Task 5: 文档同步、全量验证与全局 hook smoke

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/prd/PRD-0001-stop-hook-v-task-classifier.md`
- Modify: `docs/superpowers/specs/2026-04-19-stop-hook-provider-chain-design.md`
- Modify: `hooks/.env.example`

- [ ] **Step 1: 做文档缺口检查**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; rg -n "HOOK_PROVIDER_1_|chat_completions_stream|provider_attempt|provider chain" README.md AGENTS.md docs/prd/PRD-0001-stop-hook-v-task-classifier.md docs/superpowers/specs/2026-04-19-stop-hook-provider-chain-design.md
```

Expected:

- 在文档回写前，至少部分关键术语缺失或表述未对齐。

- [ ] **Step 2: 回写文档**

`README.md`

```markdown
## Provider Chain

The hook supports numbered providers:

- `HOOK_PROVIDER_1_*`
- `HOOK_PROVIDER_2_*`

Each provider declares `WIRE_APIS`, for example:

    HOOK_PROVIDER_1_WIRE_APIS=responses,chat_completions_stream

When `/responses` returns an empty body, the hook may fall back to `chat_completions_stream` or the next provider.
```

`AGENTS.md`

```markdown
- If `HOOK_PROVIDER_1_*` exists, the hook must treat it as the primary provider chain entry and may fall back across declared wire APIs and subsequent providers.
- Global refresh must go through `uv run python scripts\\install_global_stop_hook.py --smoke`; do not hand-copy the hook as the normal workflow.
```

- [ ] **Step 3: 跑全量验证**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest -q
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_doc_done.json | uv run python hooks\stop_v_task_classifier.py
```

Expected:

- `pytest` 全绿。
- docs fixture 输出 `{"continue": true, "decision": "block", "reason": ...}`。

- [ ] **Step 4: 安装到全局 hook 并 smoke**

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --smoke
```

Expected:

- 安装脚本只同步必要文件。
- 全局 hook docs fixture smoke 输出 docs continuation JSON。

- [ ] **Step 5: Commit**

```powershell
cd E:\development\tashan-development-hooks-loop ; git add README.md AGENTS.md docs/prd/PRD-0001-stop-hook-v-task-classifier.md docs/superpowers/specs/2026-04-19-stop-hook-provider-chain-design.md hooks/.env.example ; git commit -m "v3: doc: sync provider chain compatibility docs"
```

## Risks

- 不同 provider 的 SSE 结构可能并非完全一致；首版只覆盖当前已观测到的 `choices[0].delta.content` 变体。
- provider chain 会增加最坏情况下的 stop hook 延迟。
- 如果 provider 同时在 `/responses` 与 `chat_completions_stream` 上都行为异常，最终仍只能通过日志定位，无法自动修复。

## Review Checklist

- [ ] `.env.example` 同时覆盖 legacy `OPENAI_*` 与链式 `HOOK_PROVIDER_*`
- [ ] `load_provider_chain_settings()` 在无链式配置时兼容旧配置
- [ ] `responses` 空 body 会触发 fallback，而不是直接终止
- [ ] `chat_completions_stream` 能从 SSE 正确拼出最终文本
- [ ] 主 provider 全失败后会切 backup provider
- [ ] attempt 级日志包含 provider / wire api / text_length / error 摘要
- [ ] 聚合失败错误包含所有 `(provider, wire_api)` 尝试
- [ ] 全量测试通过
- [ ] 本地与全局 docs fixture smoke 均通过
