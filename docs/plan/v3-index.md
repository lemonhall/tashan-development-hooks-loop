# v3-index

## 愿景

当前 `v3` 聚焦 hook 传输层兼容性收敛，不改业务分类语义，只解决“同一套 classifier 在不同 provider / protocol 组合下能否稳定跑通”：

- 在不改变三类完成态判定的前提下，引入多供应商主备链
- 允许每个供应商显式声明协议尝试顺序
- 在 `responses` 不兼容、空 body、或必须 `chat.completions stream` 的场景下自动 fallback
- 让 `gpt-5.4` 在新旧供应商之间切换时，hook 尽可能自动跑通

上游设计与需求定义见：

- `../superpowers/specs/2026-04-19-stop-hook-provider-chain-design.md`
- `../prd/PRD-0001-stop-hook-v-task-classifier.md`

## 里程碑

| 里程碑 | 范围 | DoD | 验证 | 状态 |
|---|---|---|---|---|
| M1: provider chain 配置层 | 编号 provider 配置、`WIRE_APIS` 顺序、legacy `OPENAI_*` 回退、`.env.example` 同步 | `load_provider_chain_settings()` 可读链式与 legacy 配置；`.env.example` 覆盖链式键；配置解析有单测 | `uv run pytest tests\\test_stop_v_task_classifier.py -q` | todo |
| M2: 单 provider 多协议 fallback | `responses` transport、`chat_completions_stream` transport、provider 内协议切换 | `/responses` 空 body 时自动切到 `chat_completions_stream` 并成功取回 classifier JSON | `uv run pytest tests\\test_stop_v_task_classifier.py -q`；`Get-Content -Raw tests\\fixtures\\stop_payload_doc_done.json \| uv run python hooks\\stop_v_task_classifier.py` | todo |
| M3: 多 provider 主备 + 诊断 | 主 provider 全失败后切 backup provider、attempt 日志、聚合错误、全局脚本同步 smoke | 主备切换与 attempt 日志均可验证；聚合错误可定位边界；全量测试与全局 smoke 通过 | `uv run pytest -q`；`uv run python scripts\\install_global_stop_hook.py --smoke` | todo |

## 计划索引

- `./v3-stop-hook-provider-chain.md`

## 追溯矩阵

| Req ID / Infra | 覆盖里程碑 | v3 Plan | tests / commands | 证据 | 状态 |
|---|---|---|---|---|---|
| REQ-0001-002 | M2 / M3 | `v3-stop-hook-provider-chain.md` Task 2-4 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-008 | M1 | `v3-stop-hook-provider-chain.md` Task 1 | `uv run pytest tests\\test_stop_v_task_classifier.py -q` | 待实现 | todo |
| REQ-0001-009 | M1 | `v3-stop-hook-provider-chain.md` Task 1, 5 | `uv run pytest tests\\test_stop_v_task_classifier.py -q` | 待实现 | todo |
| REQ-0001-010 | M1 | `v3-stop-hook-provider-chain.md` Task 1, 5 | `uv run pytest tests\\test_stop_v_task_classifier.py -q` | 待实现 | todo |
| INFRA-provider-chain | M1 / M2 / M3 | `v3-stop-hook-provider-chain.md` Task 1-5 | `uv run pytest -q`；local/global smoke | spec 已批准 | todo |

## ECN 索引

- 当前无 ECN

## 差异列表

- `v3` 不做 session 级防重入 / 防循环状态机
- `v3` 不引入 provider-specific 硬编码名单
- `v3` 聚焦“跑通 provider / protocol 组合”，不改变三类 classifier 的业务判定规则

## Review Notes

- `v3` 的交付边界是 transport compatibility 与 provider failover，不是新 classifier，也不是 prompt 语义扩张。
- 全局安装验证遵循仓库 installer 工作流：`uv run python scripts\\install_global_stop_hook.py --smoke`。
