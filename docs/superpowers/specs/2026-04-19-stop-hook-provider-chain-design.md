# 2026-04-19 Stop Hook Provider Chain Design

## Context

目标目录：`E:\development\tashan-development-hooks-loop`

当前 `Stop hook` 已经具备三类完成态分类能力：

- `v_doc_writing_done`
- `v_milestone_done`
- `v_task_fully_done`

并且 docs 分支已经改成官方 Stop continuation 输出：

```json
{"continue": true, "decision": "block", "reason": "..."}
```

这次设计不改变分类语义本身，而是解决传输层兼容性问题：同一个 hook 需要在多个 OpenAI-compatible 供应商之间切换，并且某些供应商虽然支持同一模型名，但对不同 wire API 的实现并不一致。

本轮已确认的真实现象：

- 某新供应商的 `gpt-5.4` 在 `/v1/responses` 上返回 `HTTP 200 + empty body`
- 同一供应商的 `/v1/chat/completions` 对 `gpt-5.4` 返回 `400 Stream must be set to true`
- 同一供应商在 `stream=true` 时可以正常输出 SSE chunk

因此，问题不是“模型名不存在”，而是“不同 provider / wire API 组合存在真实不兼容”。

## Goal

把当前 hook 的单一 provider、单一传输协议调用，升级为：

- 多供应商主备链
- 每个供应商可显式声明协议尝试顺序
- 在满足预定义 fallback 规则时，自动切下一个协议或下一个供应商
- 全部失败时，输出明确、可追溯的错误摘要

最终目标不是“把错误写得更漂亮”，而是让 hook 在老供应商、新供应商之间切换时，尽可能自动跑通。

## Non-Goals

- 不改变三类 classifier 的业务判定规则
- 不改变 docs 分支 continuation prompt 文案
- 不引入 provider-specific hardcode if/else 名单
- 不做自动健康检查服务或后台守护进程
- 不做无限重试
- 不做 session 级防重入 / 防循环状态机

## Why This Exists

当前实现的瓶颈在于把“模型调用”假设成了单一路径：

- 单个 `base_url`
- 单个 `api_key`
- 单个 `model`
- 单个 `Responses API`

这在 provider 完全兼容时足够简单，但一旦遇到以下任一情况就会失效：

- `/responses` 空 body
- `/responses` 返回非 JSON
- 只支持 `chat.completions`
- 只支持 `chat.completions` 且必须 `stream=true`
- 主供应商短时异常而备供应商正常

因此需要把“传输层”从“分类层”中解耦。

## Chosen Approach

采用显式 `provider chain + wire-api chain`：

1. `.env` 中使用编号配置 `HOOK_PROVIDER_1_*`, `HOOK_PROVIDER_2_*`, ...
2. 每个 provider 配置自己的 `BASE_URL / API_KEY / MODEL / WIRE_APIS`
3. 运行时按 provider 编号顺序尝试
4. 对每个 provider，按 `WIRE_APIS` 顺序尝试
5. 某次尝试成功后立即停止后续尝试
6. 仅当命中允许 fallback 的错误类型时，继续尝试
7. 所有尝试都失败后，抛出汇总错误

这是当前最小但可扩展的结构：

- 比“只做单供应商协议 fallback”更稳
- 比“只做多供应商单协议”更能覆盖真实兼容性裂缝
- 不需要在代码里硬编码某个域名只能走某个协议

## Configuration Design

### New Chain Format

每个 provider 使用同一组键：

```dotenv
HOOK_PROVIDER_1_NAME=primary
HOOK_PROVIDER_1_BASE_URL=https://api-vip.codex-for.me/v1
HOOK_PROVIDER_1_API_KEY=sk-...
HOOK_PROVIDER_1_MODEL=gpt-5.4
HOOK_PROVIDER_1_WIRE_APIS=responses,chat_completions_stream

HOOK_PROVIDER_2_NAME=backup
HOOK_PROVIDER_2_BASE_URL=https://www.right.codes/codex/v1
HOOK_PROVIDER_2_API_KEY=sk-...
HOOK_PROVIDER_2_MODEL=gpt-5.4-high
HOOK_PROVIDER_2_WIRE_APIS=responses
```

### Required Fields Per Provider

- `NAME`
  - 仅用于日志与诊断
- `BASE_URL`
  - 允许 provider root、`/v1`、或误贴的 `/v1/responses`
  - 继续复用当前标准化逻辑
- `API_KEY`
- `MODEL`
- `WIRE_APIS`
  - 逗号分隔的显式顺序列表

### Supported Wire API Values

首版只支持两种：

- `responses`
- `chat_completions_stream`

后续如果要扩展：

- `chat_completions`
- `responses_stream`
- provider 自定义兼容层

也只是在同一枚举体系上新增，不推翻结构。

### Backward Compatibility

如果 `.env` 中不存在 `HOOK_PROVIDER_1_BASE_URL`，则继续走现有单 provider 配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

并将其内部映射为一个隐式 provider：

- `name = "default"`
- `wire_apis = ["responses"]`

这样旧配置不需要立刻迁移。

## Runtime Design

### Layer Split

运行时拆成三层：

1. **Config Layer**
   - 从 `.env` 读取 provider chain
   - 标准化 base URL
   - 校验字段完整性

2. **Transport Layer**
   - 根据 `wire_api` 调用模型并返回原始文本
   - 不做 classifier JSON 业务解释

3. **Classifier Layer**
   - 接收 transport 返回的文本
   - 解析 JSON
   - 校验 `classifier_id / is_match`

这样 transport 出问题时，不会污染 classifier 语义逻辑。

### Attempt Order

伪流程：

```text
for provider in providers:
  for wire_api in provider.wire_apis:
    try:
      text = call_transport(provider, wire_api, prompt, message)
      result = parse_classifier_json(text)
      success -> stop
    except retryable_error:
      continue to next wire_api
    except non_retryable_for_this_attempt:
      continue to next provider

if all attempts failed:
  raise aggregated error
```

### Success Contract

某次 attempt 只有在同时满足以下条件时才算成功：

1. transport 成功返回文本
2. 文本不是空串
3. 文本可以解析为 JSON
4. JSON 中包含至少：
   - `classifier_id`
   - `is_match`

否则该 attempt 视为失败。

## Transport Design

### Transport A: `responses`

调用方式：

- 继续使用 `openai.OpenAI(...).responses.create(...)`

成功提取方式：

- SDK `Response.output_text`
- 或 provider 返回 raw SSE string，再沿用现有 `response.output_text.done / delta` 提取逻辑

失败条件：

- 空 body
- 空字符串
- 非 JSON
- 非预期 SSE
- 4xx / 5xx / timeout / network error

### Transport B: `chat_completions_stream`

调用方式：

- 直接对 `/chat/completions` 发送 `stream=true`
- 使用 SSE 逐块读取

请求结构：

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "<classifier prompt>"},
    {"role": "user", "content": "<last_assistant_message>"}
  ],
  "stream": true
}
```

响应提取方式：

- 解析 `data: {...}` 行
- 从 `choices[0].delta.content` 累积文本
- 遇到 `data: [DONE]` 结束

成功条件：

- 至少得到非空最终文本

失败条件：

- SSE 格式错误
- 没有任何可用 `delta.content`
- 网络中断 / timeout
- 非 2xx

## Fallback Rules

### Retryable / Fallback-Allowed

以下情况允许切下一个协议；若当前 provider 没有剩余协议，则切下一个 provider：

- `/responses` 返回空 body
- 非 JSON
- 非预期 SSE
- 网络错误
- 超时
- 5xx
- 明确协议不兼容的 4xx
  - 例如 `Stream must be set to true`
- 明确配置错误
  - 例如 `invalid api key`
  - `model not found`

这里“配置错误也允许切 provider”是有意设计：

- 因为你现在确实可能在不同 provider 上使用不同 key / model
- 当前目标是“尽量跑通”，不是“死守当前 provider”

### No Infinite Retry

- 同一 `(provider, wire_api)` 只尝试一次
- 不做指数退避
- 不在 hook 内循环重试

原因：

- hook 是 stop-path，同步阻塞
- 当前重点是切路径，不是重试同一路径

## Logging Design

新增诊断事件：

- `provider_attempt`
  - `provider_name`
  - `base_url`
  - `wire_api`
  - `model`
- `provider_attempt_failure`
  - `provider_name`
  - `wire_api`
  - `error_type`
  - `error_message`
- `provider_attempt_success`
  - `provider_name`
  - `wire_api`
  - `text_length`
- `provider_chain_failure`
  - 所有 attempt 摘要列表

日志要求：

- 不写出完整 API key
- 不写出完整 assistant message
- 对返回文本只记录长度，不记录全文

## Error Surface

全部 provider 都失败时，最终错误应类似：

```text
All provider attempts failed:
1. primary/responses -> empty response body for /responses
2. primary/chat_completions_stream -> SSE parse failed
3. backup/responses -> model not found
```

这样你看日志时不用再靠 traceback 猜边界。

## Test Plan

需要新增以下测试：

1. **Config parsing**
   - 能从 `HOOK_PROVIDER_1_*` / `HOOK_PROVIDER_2_*` 读出链式配置
   - 不存在链式配置时，能回退到 `OPENAI_*`

2. **Responses empty body fallback**
   - provider 1 的 `responses` 返回空字符串
   - provider 1 的 `chat_completions_stream` 返回有效 SSE
   - 最终整体成功

3. **Provider failover**
   - provider 1 的所有 wire API 都失败
   - provider 2 的 `responses` 成功
   - 最终整体成功

4. **Aggregated failure**
   - 所有 provider / wire API 都失败
   - 断言最终错误含完整 attempt 摘要

5. **Log events**
   - 断言新增 `provider_attempt*` 事件存在

## Risks

### Risk 1: Provider Behavior Is Internally Inconsistent

同一 provider 可能：

- `/models` 正常
- `/responses` 空 body
- `/chat/completions` 必须 stream

这正是本设计要解决的对象，但也意味着测试必须以 transport 行为为准，不能只信 provider 文档。

### Risk 2: SSE Variants Differ

不同 provider 的 SSE 字段名可能略有差异。首版先支持当前已观察到的 OpenAI-compatible `chat.completion.chunk` 结构；若后续发现新变体，再按 transport 层扩展。

### Risk 3: Hook Latency Increases

provider chain 会让最坏情况变慢，因为可能尝试多次请求。首版接受这个成本，优先保可用性。

## Acceptance

设计落地后，以下场景应成立：

- 老供应商仅支持 `responses` 时，hook 正常工作
- 新供应商 `responses` 空 body、但 `chat_completions_stream` 可用时，hook 自动 fallback 并成功
- 主供应商全失败、备供应商可用时，hook 自动切备并成功
- 全部失败时，日志和最终错误足以直接看出每次尝试的边界

## Output

本设计批准后，将进入下一步实现计划，覆盖：

- `.env` 链式配置格式
- provider chain 运行逻辑
- `responses` transport
- `chat_completions_stream` transport
- 日志扩展
- 测试补齐

## Review Notes

这份 spec 只定义传输层兼容性方案，不直接修改当前业务判定规则。它的目标是让现有 classifier 在不同 provider 之间更稳地“跑起来”，而不是扩大 hook 的业务职责。
