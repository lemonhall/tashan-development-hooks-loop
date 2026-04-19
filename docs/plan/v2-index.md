# v2-index

## 愿景

当前 `v2` 不是新功能开发，而是一个最小文档闭环：

- 在 `docs/plan/` 下补齐一组新的 `v2` 文档
- 让最终收尾回复可以明确表达“本轮文档已完成”
- 为 `Stop hook` 的 `v_doc_writing_done` 分支提供一个干净、低风险的 smoke 场景

上游设计与需求定义仍沿用：

- `../prd/PRD-0001-stop-hook-v-task-classifier.md`
- `../superpowers/specs/2026-04-19-stop-hook-ai-classifier-design.md`

## 里程碑

| 里程碑 | 范围 | DoD | 验证 | 状态 |
|---|---|---|---|---|
| M1: v2 文档落盘 | 创建 `v2-index` 与单个 `v2` 计划文档 | 两个文件都存在，且包含塔山循环要求的最小结构；不修改任何源码与测试 | 人工读回文档；`git diff --text -- docs/plan/v2-index.md docs/plan/v2-stop-hook-doc-smoke.md` | done |

## 计划索引

- `./v2-stop-hook-doc-smoke.md`

## 追溯矩阵

| Req ID | v2 Plan | tests / commands | 证据 | 状态 |
|---|---|---|---|---|
| REQ-0001-003 | M1 / 文档 smoke | `git diff --text -- docs/plan/v2-index.md docs/plan/v2-stop-hook-doc-smoke.md` | `v2` 文档已落盘，最终回复可输出明确完成信号 | done |
| REQ-0001-004 | M1 / 文档 smoke | 人工检查 `v2` 文档与最终回复 | `v2` 被明确标记为文档完成，不混淆为 milestone 或 full task | done |
| REQ-0001-007 | M1 / 文档 smoke | 人工检查最终收尾文本 | 本轮目标是为 docs 分支提供一个明确正例 | done |

## ECN 索引

- 当前无 ECN

## 差异列表

- 当前无遗留差异；`v2` 的范围仅限文档 smoke

## Review Notes

`v2` 在本轮刻意保持“只写文档、不改代码、不做 live smoke”的收敛范围，目标只是产出一组可被 hook 识别为文档完成的版本化文档。
