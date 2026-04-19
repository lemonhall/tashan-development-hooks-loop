# v2 Stop Hook Doc Smoke Plan

**Goal:** 在不改动现有实现的前提下，新增一组最小 `v2` 文档，让本轮交付可以稳定表达“文档写作完成”，用于本地 `Stop hook` smoke。

## PRD Trace

- 这不是新的需求实现，而是一个文档型 smoke 场景
- 复用并服务于已有行为验证：
  - `REQ-0001-003`：分类输入应能从最终回复中读到明确完成语义
  - `REQ-0001-004`：三种完成状态需要有清晰边界
  - `REQ-0001-007`：命中完成判定时应走正确分支提示

## Scope

- 新增 `docs/plan/v2-index.md`
- 新增 `docs/plan/v2-stop-hook-doc-smoke.md`
- 用最小但完整的塔山结构写清本轮愿景、范围、验收和风险

## Non-Goals

- 不修改 `hooks/stop_v_task_classifier.py`
- 不新增或修改 `tests/fixtures/`
- 不运行 live API smoke
- 不触碰全局 hook 安装

## Acceptance

1. `docs/plan/v2-index.md` 存在，且至少包含：愿景、里程碑、计划索引、追溯矩阵、ECN 索引、差异列表。
2. `docs/plan/v2-stop-hook-doc-smoke.md` 存在，且至少包含：Goal、PRD Trace、Scope、Non-Goals、Acceptance、Files、Steps、Risks。
3. 本轮变更仅限 `docs/plan/` 下新增两个 `v2` 文件，不修改源码、测试、fixture、安装脚本或 secrets。
4. 最终收尾文本可以在不自相矛盾的前提下发出 `v_doc_writing_done` 完成信号。

## Files

- Create: `docs/plan/v2-index.md`
- Create: `docs/plan/v2-stop-hook-doc-smoke.md`

## Steps

1. **Analysis**
   - 读取现有 `v1-index.md`
   - 确认仓库已有 `PRD-0001` 与 design spec 可供 `v2` 引用
2. **Draft**
   - 先写 `v2-index.md`，明确这是文档 smoke
   - 再写 `v2-stop-hook-doc-smoke.md`，补齐范围、验收与风险
3. **Review**
   - 读回两个新文件，确认关键段落齐全
   - 确认没有写入任何“还差一步才算完成”的尾项
4. **Close**
   - 以“本轮文档已完成”的自然语言收尾
   - 在最终回复中附上 `TASHAN_COMPLETION_SIGNAL`

## Risks

- 如果收尾回复里混入“后续再做 live smoke / push / merge”等尾项，hook 可能不应把本轮判成 done。
- 如果 `v2` 文档范围写得太大，最终就不能诚实地只发 `v_doc_writing_done`。
- 如果把本轮描述成 milestone 或 full task 完成，可能干扰三分支优先级的本地测试。
