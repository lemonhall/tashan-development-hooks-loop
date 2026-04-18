# v1-index

## 愿景

当前 `v1` 面向一个最小闭环：

- 让 `Stop hook` 读取 `last_assistant_message`
- 用多套二次 AI 分类判断：
  - 文档写作是否完成
  - 某个 `M` 是否完成
  - 整个 `v` 系列是否完成
- 命中时显示对应分支提示语

上游设计与需求定义见：

- `../superpowers/specs/2026-04-19-stop-hook-ai-classifier-design.md`
- `../prd/PRD-0001-stop-hook-v-task-classifier.md`

## 里程碑

| 里程碑 | 范围 | DoD | 验证 | 状态 |
|---|---|---|---|---|
| M1: 文档完成分支 | 项目骨架、secrets 边界、`v_doc_writing_done`、文档完成 fixture | 文档写作完成正例命中 docs 分支提示语；一般进行中反例静默放行；`.env` 不进 git | `uv run pytest -q`；`Get-Content -Raw tests\\fixtures\\stop_payload_doc_done.json \| uv run python hooks/stop_v_task_classifier.py` | todo |
| M2: 单个里程碑完成分支 | `v_milestone_done`、milestone fixture、分支输出 | `M2 已完成但 v1 未完成` 正例命中 milestone 分支；full-v 分类不得误判为 true | `uv run pytest -q`；`Get-Content -Raw tests\\fixtures\\stop_payload_milestone_done.json \| uv run python hooks/stop_v_task_classifier.py` | todo |
| M3: 整体 v 完成分支 | `v_task_fully_done`、优先级聚合、最终 smoke | 整体 `v1` 完成正例命中 task 分支；多分支同时命中时 task 分支优先；四类 fixture 全部通过 | `uv run pytest -q`；`Get-Content -Raw tests\\fixtures\\stop_payload_v_task_done.json \| uv run python hooks/stop_v_task_classifier.py`；`Get-Content -Raw tests\\fixtures\\stop_payload_not_done.json \| uv run python hooks/stop_v_task_classifier.py` | todo |

## 计划索引

- `./v1-stop-hook-ai-classifier.md`

## 追溯矩阵

| Req ID | v1 Plan | tests / commands | 证据 | 状态 |
|---|---|---|---|---|
| REQ-0001-001 | M1 / M2 / M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-002 | M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-003 | M1 / M2 / M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-004 | M1 / M2 / M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-005 | M2 | `Get-Content -Raw tests\\fixtures\\stop_payload_milestone_done.json \| uv run python hooks/stop_v_task_classifier.py` | 待实现 | todo |
| REQ-0001-006 | M2 / M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-007 | M1 / M2 / M3 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-008 | M1 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-009 | M1 | `uv run pytest -q` | 待实现 | todo |
| REQ-0001-010 | M1 | `uv run pytest -q` | 待实现 | todo |

## ECN 索引

- 当前无 ECN

## 差异列表

- `v1` 不包含 continuation 自动注入用户提示词
- `v1` 不读取 transcript tail
- `v1` 已要求同时支持“文档写作完成”、“单个 M 完成”和“整体 `v` 完成”三类判定
- 官方文档截至 `2026-04-19` 仍声明 Windows hooks 暂未支持，这一风险尚未被实现层消解

## Review Notes

`v1` 当前只完成文档与计划收敛，尚未进入实现与验证阶段。
