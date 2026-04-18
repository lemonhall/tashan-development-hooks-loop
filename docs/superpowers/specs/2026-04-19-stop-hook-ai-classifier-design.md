# 2026-04-19 Stop Hook AI Classifier Design

## Context

目标目录：`E:\development\tashan-development-hooks-loop`

目标是为 `Codex Stop hook` 设计一个可扩展但一次性交付到位的 `v1` 闭环：

1. `Stop` 事件触发；
2. Hook Python 脚本从 stdin 读取官方 payload；
3. 取出 `last_assistant_message`；
4. 用 Python `openai` SDK 调一次 `Responses API`；
5. 让模型根据不同分类目标判断这段最终回复；
6. `v1` 至少同时支持三个分类目标：
   - `v_doc_writing_done`
   - `v_milestone_done`
   - `v_task_fully_done`
7. 如果任一目标命中，则按优先级返回分支提示语。

## Why This Exists

用户当前痛点不是“怎么写一个普通 hook”，而是：

- 官方 hooks 文档抽象，难以直接落地；
- 纯关键词匹配对“v 系列是否已完成”的判断不稳；
- 需要把“完成判定”外包给第二次 AI 分类，而不是把业务语义硬编码进字符串规则里；
- 需要把分类器做成多目标结构，不能把 `v1` 做窄成只判断“文档写完了”；
- 需要显式区分“文档全部完成”、“某个 `M` 完成”、“整个 `v` 都完成”三种 stop 语义。

## Constraints

- 运行目标按用户要求包含原生 Windows 11，不因官方限制而从 `v1` 范围中排除。
- 但官方文档截至 `2026-04-19` 仍写明：
  - `Codex hooks` 处于 `Experimental`
  - `Windows support temporarily disabled`
- `v1` 仍只以 `last_assistant_message` 作为分类输入主载体，不引入 transcript 全量分析。
- `v1` 只做“显示固定提示语”，不做自动 continuation 注入。
- Python 脚本不内联真实密钥，改为读取脚本同级目录 `.env`。
- 仓库必须忽略真实 `.env`，并提供 `.env.example` 占位模板。
- 用户尚未提供“整个 `v` 系列代码全部完成”的现成样本，因此 `v1` 自身必须拆成至少 3 个 `M`，让开发过程自然产出三类 stop 样本。

官方参考：

- `https://developers.openai.com/codex/hooks`
- `https://platform.openai.com/docs/api-reference/responses/create`

## Approaches Considered

### Approach A: 纯规则 / 关键词匹配

做法：

- 直接在 hook 脚本中查找 `v25`、`完成`、`done`、`已交付` 等词。

优点：

- 实现最简单；
- 不依赖二次 API 调用。

缺点：

- 语义漂移大；
- assistant 只要措辞稍变就会误判；
- 与用户明确要求不一致。

结论：不选。

### Approach B: 单一分类器

做法：

- 只支持一个分类目标；
- Hook 每次只跑一套提示词。

优点：

- 结构简单；
- 实现最简单。

缺点：

- 无法同时覆盖“文档写作完成”和“整个 `v` 系列全部完成”；
- 后续加第二类判定时会回到结构重写。

结论：不选。

### Approach C: 多分类目标 + 同一输入源

做法：

- 每次 `Stop` 都读取同一份 `last_assistant_message`；
- 对这段文本顺序运行多套 classifier prompt；
- `v1` 最低内置三套：
  - `v_doc_writing_done`
  - `v_milestone_done`
  - `v_task_fully_done`
- 每套 classifier 都输出统一 JSON；
- Hook 聚合结果并决定是否返回固定提示语。

优点：

- 符合用户要的“不是单一分类器”；
- `v1` 一次把接口、结构和三类核心判定都做出来；
- 后续再加其他分类目标时，不需要推翻主链。

缺点：

- 比单一分类器多一层结构设计；
- “整个 `v` 系列全部完成”这套提示词当前缺少用户提供的高质量样本，只能先写初版规则；
- 需要处理多分支同时命中的优先级。

结论：`v1` 采用。

### Approach D: `last_assistant_message` + transcript tail + 多分类目标

做法：

- 除最终回复外，再读取最近几轮 transcript 作为补充上下文；
- 再交给分类模型判断。

优点：

- 判定更稳；
- 能减少“最终回复措辞不完整”的误判。

缺点：

- 输入边界更复杂；
- `v1` 先不用把上下文裁剪逻辑、隐私边界、token 成本一起引入。

结论：留给后续版本。

## Chosen Design

### Runtime Flow

1. `Codex` 触发 `Stop` hook。
2. `hooks/stop_v_task_classifier.py` 从 stdin 读取 JSON payload。
3. 读取 `payload["last_assistant_message"]`。
4. 从脚本同级 `.env` 读取：
   - `OPENAI_API_KEY`
   - `OPENAI_BASE_URL`
   - `OPENAI_MODEL`
5. 使用 `openai` Python SDK 调 `Responses API`。
6. Hook 加载 classifier registry。
7. `v1` registry 至少包含两个 classifier：
   - `v_doc_writing_done`
   - `v_milestone_done`
   - `v_task_fully_done`
8. 对每个 classifier：
   - 使用该 classifier 的系统提示词；
   - 用户输入只包含 `last_assistant_message`；
   - 调一次 `Responses API`；
   - 要求输出统一 JSON。
9. 统一 JSON 字段：
   - `classifier_id: string`
   - `is_match: boolean`
   - `version: string | null`
   - `milestone_id: string | null`
   - `reason: string`
10. Hook 聚合全部 classifier 结果。
11. 若多个 classifier 同时命中，按优先级选择一个输出：
   - `v_task_fully_done`
   - `v_milestone_done`
   - `v_doc_writing_done`
12. 分支消息：
   - `v_doc_writing_done`: `hello World from hooks, on stop event, and v docs have done`
   - `v_milestone_done`: `hello World from hooks, on stop event, and v milestone has done`
   - `v_task_fully_done`: `hello World from hooks, on stop event, and v task has done`
13. 若全部 classifier 的 `is_match=false`，静默放行，不显示该消息。

### Prompt Contract

`v1` 的分类模型提示词必须满足：

- 每个 classifier 只做一个判断；
- 不做建议生成；
- 不做额外长解释；
- 输出必须是单个 JSON 对象；
- 不允许 markdown 包裹；
- 若回复只表示“分析中 / 进行中 / 已完成部分工作 / 还需用户确认”，则判定为 `false`。

#### `v_doc_writing_done`

判定目标：

- 判断 assistant 最终回复是否明确表明某个 `v` 系列任务的文档写作阶段已经完成。

正向信号：

- 明确写出“文档已经写到目标目录了 / 已经落盘 / 核心产物在这里 / PRD 和 plan 已写好”
- 明确写出“已经改回去了 / 已回写 / 已更新到文档 / 改动已经落到这些文档文件里”
- 列出具体文档产物或路径
- 明确邀请用户审阅这些文档
- 明确表示“实现是下一步”，但文档阶段本身已经完成

补充规则：

- 若回复里出现 `v1-index.md`、`v25-*.md` 等带版本号的文档文件名或路径，classifier 可以据此提取 `version`

#### `v_milestone_done`

判定目标：

- 判断 assistant 最终回复是否明确表明某个 `vN` 下面的单个里程碑 `M` 已完成。

正向信号：

- 明确写出 `M1`、`M2`、`M3` 或类似里程碑编号已完成
- 明确说“这一阶段 / 这个 M / 该 milestone 已完成”
- 允许同时说明整个 `v` 尚未完成

负向硬规则：

- 如果回复只表示正在做某个 `M`，必须判定为 `false`
- 如果回复没有明确里程碑编号或等价 milestone 标识，必须判定为 `false`
- 如果回复只是列出 `M1 / M2 / M3` 作为计划、拆分或后续执行顺序，而没有明确说某个 `M` 已完成，必须判定为 `false`

#### `v_task_fully_done`

判定目标：

- 判断 assistant 最终回复是否明确表明某个 `v` 系列任务的整体交付已经完成，而不是只完成其中一个 `M`、一个 slice、一个子任务或文档阶段。

负向硬规则：

- 如果回复只表示“某个 `M` 完成了”或“完成了一部分代码 / 文档 / 测试”，必须判定为 `false`
- 如果回复明确说“下一步还要继续实现 / 测试 / 验证 / 收尾”，必须判定为 `false`
- 只有当回复语义指向“整个 `vN` 范围都完成了”时，才允许判定为 `true`

## v1 Milestone Decomposition

`v1` 本身必须拆成至少 3 个 `M`，用于在真实开发过程中自然收集 stop 样本：

- `M1: 文档写作完成分支`
  - 建立项目、PRD / plan、`.env` / `.gitignore` 契约
  - 实现 `v_doc_writing_done`
  - 该阶段完成时形成“文档写作完成”真实样本
- `M2: 单个里程碑完成分支`
  - 实现 `v_milestone_done`
  - 该阶段完成时形成“某个 M 完成，但整个 v 未完成”真实样本
- `M3: 整体 v 完成分支`
  - 实现 `v_task_fully_done`
  - 实现优先级聚合与最终 smoke
  - 该阶段完成时形成“整个 v 完成”真实样本

### File Boundaries For v1 Implementation

预期实现文件边界：

- `hooks/stop_v_task_classifier.py`
  - Stop hook 入口
  - payload 读取
  - `.env` 读取
  - classifier registry
  - Responses API 调用
  - hook 输出生成
- `hooks/.env.example`
  - 本地配置模板
- `.gitignore`
  - 忽略真实 `.env`
- `tests/fixtures/stop_payload_doc_done.json`
  - 文档写作完成正例
- `tests/fixtures/stop_payload_milestone_done.json`
  - 某个 `M` 完成正例
- `tests/fixtures/stop_payload_v_task_done.json`
  - 整个 `v` 系列完成正例
- `tests/fixtures/stop_payload_not_done.json`
  - 一般进行中的反例
- `tests/test_stop_v_task_classifier.py`
  - 单元测试 / 契约测试

## Acceptance Preview

`v1` 交付完成的最低判断标准：

- 给一个明确表示“文档已经写到目标目录 / PRD 与计划已落盘”的示例 payload，脚本输出固定提示语；
- 给一个明确表示“某个 `M` 已完成，但整个 `v` 尚未完成”的示例 payload，脚本输出 milestone 分支提示语；
- 给一个明确表示“整个 `v25` 全部完成”的示例 payload，脚本输出固定提示语；
- 给一个只表示“还在进行中”的示例 payload，脚本不输出固定提示语；
- `.env` 不进 git，`.env.example` 存在；
- 文档里明确写出 Windows 运行风险，而不是假装官方已支持。

## Non-Goals

- 不做 continuation 自动插入用户提示词；
- 不做 transcript 全量读取；
- 不做多模型投票；
- 不做 prompt 自动自修复；
- 不处理移动端推送或其他通知链。

## Risks

### Risk 1: Windows Runtime Risk

官方文档截至 `2026-04-19` 仍声明 Windows hooks 暂未支持。即使本方案按 Windows 作为目标运行面设计，也必须把这一点记入 PRD 和计划文档。

### Risk 2: Model Classification Drift

二次 AI 分类仍可能因提示词不足而误判。`v1` 先接受这一风险，并通过：

- 严格 JSON 输出；
- 明确正反例测试；
- 把“文档完成”和“整体 `v` 完成”拆成不同 classifier；
- 把“单个 `M` 完成”作为独立 classifier；
- 把“单个 `M` 完成不等于整个 `v` 完成”写成 `v_task_fully_done` 的硬规则；

来压低误判率。若仍不稳，后续再引入 transcript tail 或更强上下文。

## Output Documents

本设计批准后落盘以下文档：

- `docs/prd/PRD-0001-stop-hook-v-task-classifier.md`
- `docs/plan/v1-index.md`
- `docs/plan/v1-stop-hook-ai-classifier.md`

## Review Notes

这份设计只负责把需求收敛成可执行的 `PRD + v1 plan`，不直接等于实现完成。
