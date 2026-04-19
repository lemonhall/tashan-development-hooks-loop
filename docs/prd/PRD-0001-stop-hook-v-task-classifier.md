# PRD-0001: Stop Hook V Task Classifier

## 基本信息

- **PRD 编号**：PRD-0001
- **主题**：Stop hook 二次 AI 分类判定 `v` 系列任务是否完成
- **日期**：2026-04-19
- **当前阶段**：设计完成，待进入 `v1` 施工计划

## Vision

作为一名在 Windows 11 上使用 Codex 的用户，我希望在 `Stop` 事件发生时，hook 能读取 assistant 的最终回复，再通过第二次 AI 分类判断这一轮是否明确表示：

- 某个 `v` 系列任务的文档写作阶段已完成；
- 某个 `v` 系列任务下面的单个 `M` 已完成；
- 或某个 `v` 系列任务整体已完成；

若任一命中，则显示固定提示语，从而为后续 continuation 自动插入打下稳定基础。

成功长相：

- “完成”不是字符串拍脑袋判断，而是由单独的分类模型负责；
- `v1` 不是单一分类器，而是至少支持三类完成判定；
- 当前闭环只显示固定提示语，不额外扩 scope；
- 真实密钥不进入 git；
- 文档对官方 Windows 风险保持显式、诚实。

## Problem Statement

当前问题有三层：

1. 官方 hooks 文档对 stop payload 与返回语义较抽象，直接上手难；
2. 纯关键词判断“`v` 系列是否完成”不稳定；
3. “文档写作完成”、“某个 `M` 完成”和“整个 `v` 系列整体完成”不是一回事，不能用同一条模糊规则混着判；
4. 后续想做 continuation 注入前，必须先有一个最小可控、可测试、可解释的“完成判定”闭环。

## Scope

本 PRD 仅覆盖 `v1`：

- 读取 `Stop` payload 中的 `last_assistant_message`
- 用 Python `openai` SDK 调 `Responses API`
- 用多套固定提示词做多目标分类判定
- classifier prompt 在存在显式 `TASHAN_COMPLETION_SIGNAL` 时必须优先读取该信号；缺失时才回退自然语言语义
- `v1` 至少同时支持：
  - `v_doc_writing_done`
  - `v_milestone_done`
  - `v_task_fully_done`
- 若任一目标判定完成，返回对应分支提示语
- `v1` 自身拆成至少 3 个 `M`，用于在开发过程中收集三类 stop 样本
- 使用同级 `.env`
- 要求 `.gitignore` 忽略真实 `.env`
- 提供 `.env.example`

## Non-Goals

- 不做 continuation 自动插入用户提示词
- 不做 transcript 全量分析
- 不做多模型投票
- 不做 hook 递归控制
- 不解决官方 Windows hooks 支持状态

## 术语

- **Stop hook**：Codex 在对话轮次结束时触发的 hook。
- **最终回复**：`Stop` payload 中的 `last_assistant_message`。
- **`v` 系列任务**：形如 `v1`、`v5`、`v25` 的版本化任务或里程碑。
- **分类目标**：一条 classifier prompt 所负责判断的具体目标。
- **文档写作完成**：某个 `v` 系列任务的 PRD / 计划 / spec 等文档产物已经写好并落盘。
- **里程碑完成**：某个 `vN` 下面的单个 `M` 已经完成，但不代表整个 `vN` 已完成。
- **整体 `v` 完成**：某个 `v` 系列任务的整个范围已经完成，而不是只完成一个 `M`、一部分代码或文档阶段。
- **完成判定**：分类模型根据最终回复判断某个分类目标是否命中。

## Requirements

### REQ-0001-001：Stop payload 读取最终回复

**动机**

完成判定必须建立在官方 hook 输入之上，不能靠外部猜测。

**范围**

- Hook Python 脚本从 stdin 读取 `Stop` payload JSON
- 提取 `last_assistant_message`

**非目标**

- 不读取 transcript 全量内容
- 不依赖对话历史数据库

**验收口径**

- 给定一份包含 `last_assistant_message` 的模拟 payload，脚本能成功读出该字段
- 若该字段缺失，脚本必须明确失败或返回可诊断错误

### REQ-0001-002：使用 Python openai SDK 调用 Responses API

**动机**

用户已明确要求在 Python hook 脚本中直接使用 Python `openai` 库，并使用 `Responses API`。

**范围**

- 使用 Python `openai` SDK
- 发起一次二次模型调用
- hook 必须兼容标准 SDK `Response` 对象，以及供应商返回 raw SSE string 的情况；只要能从 `response.output_text.done` 或等价事件中提取最终文本即可

**非目标**

- 不改用 shell `curl`
- 不改用 Chat Completions API

**验收口径**

- 实现方案中明确出现 `openai` SDK 和 `Responses API`
- 测试或模拟验证中能替换 / mock 掉该调用

### REQ-0001-003：分类提示词只输出严格 JSON

**动机**

Hook 后续逻辑必须可程序解析，不能靠自然语言再猜一次。

**范围**

- 提示词要求模型只输出一个 JSON 对象
- 若 `last_assistant_message` 中存在 `TASHAN_COMPLETION_SIGNAL_BEGIN ... TASHAN_COMPLETION_SIGNAL_END` 显式信号块，classifier 必须优先按该信号块判定
- JSON 至少包含：
  - `classifier_id`
  - `is_match`
  - `version`
  - `milestone_id`
  - `reason`
- `v_doc_writing_done` classifier 允许根据显式版本化文档路径或文件名推断 `version`
- `v_milestone_done` classifier 必须把“只是在规划或列出 M1/M2/M3”与“某个 M 已完成”区分开
- 若显式信号块与自然语言语义冲突，以显式信号块为准

**非目标**

- 不输出 markdown
- 不输出多段解释

**验收口径**

- 正例与反例测试都以 JSON 解析为前提
- 若模型输出无法解析，脚本必须返回可诊断错误，不得静默吞掉

### REQ-0001-004：`v1` 必须支持多个分类目标

**动机**

用户已明确要求分类器不能收窄成只判断“文档都写完了”。

**范围**

- `v1` 最低内置三个分类目标：
  - `v_doc_writing_done`
  - `v_milestone_done`
  - `v_task_fully_done`
- 三者共享同一输入源：`last_assistant_message`

**非目标**

- 不要求 `v1` 支持无限动态插件化加载

**验收口径**

- 文档与计划中明确写出三个分类目标
- 测试口径中同时覆盖三个目标

### REQ-0001-005：`v_milestone_done` 必须识别单个 M 完成

**动机**

用户已明确指出：`v` 系列代码常分多个 `M`；单个 `M` 完成本身也需要被 hook 识别和处理。

**范围**

- `v_milestone_done` classifier 必须识别 “M1 / M2 / M3 已完成” 或等价 milestone 完成表述
- 若 `last_assistant_message` 中明确出现 milestone 编号，则输出中必须提取对应 `milestone_id`；若未明确出现，则返回 `null`
- 若回复只是说“接下来按 M1 / M2 / M3 去实现”或只是罗列 milestone 名称，则必须判定为 `false`

**非目标**

- 不要求在 `v1` 内精确建模所有项目的所有里程碑结构

**验收口径**

- 给定一个“单个 `M` 已完成，但整个 `v` 未完成”的示例 payload，脚本必须返回 milestone 分支提示语

### REQ-0001-006：整体 `v` 完成判定必须区分“单个 M 完成”和“整个 v 完成”

**动机**

只完成一个 `M` 不等于整个 `v` 系列完成，不能让 full-v 分支误报。

**范围**

- `v_task_fully_done` classifier 必须把“只完成一个 `M`”判为 `false`
- `v_task_fully_done` classifier 必须把“只差 live smoke / push / merge / remote 配置 / 人工确认”等尾项未闭合的回复判为 `false`
- 只有明确表明整个 `vN` 范围都完成时，才允许判为 `true`

**非目标**

- 不要求 `v1` 读取计划文档来自动计算所有 `M` 是否完成

**验收口径**

- 给定一个“单个 `M` 已完成，但整个 `v` 未完成”的示例 payload，full-v 分类结果必须为 `false`

### REQ-0001-007：命中完成判定时返回分支提示语

**动机**

`v1` 的业务目标是先建立“三类完成 -> 分支提示语”的最小闭环。

**范围**

- 当任一 classifier 的 `is_match=true` 时，返回对应分支的 `systemMessage`
- 若多个 classifier 同时命中，优先级为：
  - `v_task_fully_done`
  - `v_milestone_done`
  - `v_doc_writing_done`

**非目标**

- 不做 continuation block / reason 注入
- 不做多语言消息模板

**验收口径**

- 文档完成正例返回：
  `hello World from hooks, on stop event, and v docs have done`
- 里程碑完成正例返回：
  `hello World from hooks, on stop event, and v milestone has done`
- 整体 `v` 完成正例返回：
  `hello World from hooks, on stop event, and v task has done`
- 反例输入不得返回该消息

### REQ-0001-008：从脚本同级 `.env` 读取 AI 配置

**动机**

用户已否决把真实 key 直接写在脚本开头。

**范围**

- 读取脚本同级目录 `.env`
- 最低需要支持：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`
- `OPENAI_BASE_URL` 允许填写 provider root、标准 `/v1` base，或误贴的 `/v1/responses` 预览 URL；hook 必须规范化为可供 Python `openai` SDK `Responses API` 使用的 `/v1` base URL

**非目标**

- 不读取全局系统环境变量作为唯一来源
- 不依赖外部 secret manager

**验收口径**

- `.env` 缺失或字段缺失时，脚本必须给出明确错误
- `.env` 正常时，脚本能读取到三个必要字段
- 当 `.env` 中的 `OPENAI_BASE_URL` 为 `https://www.right.codes/codex` 时，hook 规范化后必须对 `Responses API` 使用 `https://www.right.codes/codex/v1`

### REQ-0001-009：仓库必须忽略真实 `.env`

**动机**

避免真实密钥误入 git。

**范围**

- 根目录 `.gitignore` 必须覆盖真实 `.env`

**非目标**

- 不要求处理 git 历史里已泄露的密钥

**验收口径**

- `.gitignore` 中存在对真实 `.env` 的忽略规则
- 文档中明确写出这一检查项

### REQ-0001-010：仓库必须提供 `.env.example`

**动机**

给本机手工配置留出稳定模板，避免工程师猜字段名。

**范围**

- 提供不含真实密钥的 `hooks/.env.example`

**非目标**

- 不写真实 token
- 不写用户本机专用 URL

**验收口径**

- `hooks/.env.example` 存在
- 至少包含三个占位键名：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`

## Assumptions And Constraints

- 截至 `2026-04-19`，官方文档仍声明 `Codex hooks` 为 `Experimental`，且 `Windows support temporarily disabled`。
- 尽管如此，按用户明确要求，`v1` 的目标运行面仍包含原生 Windows 11。
- `v1` 的“完成判定”只以 `last_assistant_message` 为输入主载体。
- 用户尚未提供“整体 `v` 完成”高质量样本，因此 `v1` 必须拆成至少 3 个 `M`，边开发边收集文档完成、单个 `M` 完成、整体 `v` 完成三类真实样本。

## Success Metrics

- 给一个明确表示文档写作完成的示例 payload，脚本输出 docs 分支提示语。
- 给一个明确表示单个 `M` 完成的示例 payload，脚本输出 milestone 分支提示语。
- 给一个明确表示整个 `v` 系列已完成的示例 payload，脚本输出 task 分支提示语。
- 给一个明确只表示某个 `M` 完成的示例 payload，full-v 分类器不得误判为整个 `v` 系列已完成。
- 给一个明确表示仍在进行中的示例 payload，脚本不输出固定提示语。
- `.env` 不进入 git，`.env.example` 存在。
- 文档中有显式风险记录，而不是把 Windows 支持状态写成已解决。

## Risks

### 风险 1：Windows 运行时不稳定

官方文档当前并未承诺 Windows 支持，因此 `v1` 实际运行可能受限于 Codex 自身实现状态。

### 风险 2：二次 AI 分类漂移

即使使用固定提示词，模型仍可能对语义模糊的最终回复产生误判。尤其是“单个 `M` 完成”和“整个 `v` 完成”的边界。`v1` 先通过严格 JSON 输出、三分类目标拆分、优先级聚合与正反例测试压缩风险，后续若不够稳，再增加上下文或修订提示词。

## Out Of Scope For v2 Backlog Seed

以下内容明确不纳入 `v1`，但可进入后续版本：

- transcript tail 作为额外上下文
- continuation 自动注入用户提示词
- 防重入 / 防循环控制
- 多模型交叉校验
