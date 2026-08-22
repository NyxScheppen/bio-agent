# CLAUDE.md

## 项目定位

- **合成生物学辅助 Agent**：面向生物信息学 / 合成生物学的多 agent 助手
- **双重定位**：iGEM 参赛项目 + AI Agent 求职作品集
- **核心能力**：合成生物学知识专家（RAG 增强）、多任务执行、步骤可视化、可回溯
- **架构**：LangGraph 多 agent（router → planner → executor → reporter）+ 工具注册表 + RAG + R/Python 双语言
- **设计文档**：`docs/design/2026-08-22-synthbio-agent-design.md`（架构决策的唯一权威来源）

---

## Part 1: 通用行为准则

**Tradeoff:** 这些准则偏向谨慎而非速度。对简单任务用自己的判断力。

### 1. 先想再做
- 陈述你的假设。不确定就问。
- 如果存在多种解释，列出它们——不要悄无声息地选一个。
- 如果存在更简单的方法，说出来。

### 2. 简单至上
- 只写解决问题所需的最少代码。
- 不为单次使用的代码创建抽象。
- 不添加未被要求的"灵活性"或"可配置性"。
- 如果有 200 行可以写成 50 行，重写。
- 自问："一个 senior engineer 会认为这过度设计了吗？"

### 3. 外科手术式修改
- 只改你必须改的。
- 不要"顺便改进"相邻代码、注释、格式。
- 匹配现有风格，即使你不喜欢。
- 清理你自己改动造成的 orphan（未使用的 import/变量/函数）。

### 4. 目标驱动
- 把需求转化为可验证的目标。
- 多步骤任务先列出计划，每步带验证检查点。

---

## Part 2: 编码规范

### Python

- **Python 3.11+**，严格类型注解（所有函数签名必须有完整类型标注）
- **命名**：`snake_case` 变量/函数，`PascalCase` 类，`UPPER_SNAKE` 常量
- **异步**：I/O 操作（工具 `run()`、R 子进程、LLM 调用、RAG 检索）用 `async def`。纯计算（如单基因表达统计 mean/median/sd + t 检验、`Embedder.embed`）保持同步
- **导入顺序**：标准库 → 第三方 → 本地模块（每组之间空行）
- **枚举**：用 `Enum`，如 `Category`（工具分类）、`Runtime`（python/r）
- **docstring**：公开方法用 Google style。重点解释 "why" 而非 "what"
- **LLM 客户端**：必须统一走 LangChain 封装，不直接使用 httpx
- **R 调用**：必须统一走 `backend/bioagent/r_runner.py` 的 R 执行器（`RRunner`），工具内不直接 `subprocess`
- **禁止**：`*` 导入、`except Exception` 吞异常（不重抛）、模块级可变全局变量
- **豁免（best-effort 旁路）**：观测（LangSmith）上报、SSE 事件分发等旁路增强的失败只记日志返默认值或跳过、不重抛，主流程正确性不依赖其结果

### TypeScript / React

- TypeScript 严格模式（`strict: true`）
- 组件命名 `PascalCase`，文件命名 `camelCase.tsx`
- 所有 API 端点必须有测试
- 全局状态用 Zustand stores（每个系统一个 store）
- SSE 事件流用自定义 hook（`frontend/src/hooks/useSSE.ts`）

---

## Part 3: 架构约定

这些是项目级约束，改动前先看设计文档。

### 加工具 = 加一个文件

- 新分析能力在 `backend/bioagent/tools/<category>/<tool_name>/` 下加一个 `ToolDefinition` 文件
- **不改编排层**（router/planner/executor/reporter 无感知）
- 工具对外统一「文件进、文件出」契约：输入为参数 + 文件路径，输出为结构化结果（JSON；图由前端据 result 渲染）

### 分层（禁止新增抽象层）

```
API 层 → Agent 编排层 → 工具 / 注册表 / RAG / 执行层
```

- 现有分层已足够，不要再加 Repository/Service/Manager 等额外层

### 工具分类与管线

工具 `category` 决定管线裁剪的工具子集。新增 category 需同步确认 router 的意图映射。

---

## Part 4: 测试规范

### Mock 原则

- 所有 LLM 调用处必须可注入 mock，返回预设 fixture，保证可重复
- R 工具测试 mock R 子进程，不真跑 Rscript
- 测试不依赖真实 LLM、真实 R 环境、真实文件系统
- 测试验证管道正确性（输入走对流程、输出结构正确），**不验证 LLM 输出的文本质量**

### 测试写法

- 每个工具 `run()` 的测试 ≤ 5 个断言
- 纯计算优先测且测全（如单基因表达统计 mean/median/sd + t 检验、`Embedder.embed`）
- 管线测试验证 router → … → reporter 的编排正确性
- 测试目录：`tests/test_{系统}/`

### 测试清单更新

**每次编写测试后**，必须更新 `docs/test-inventory.md`，追加：
- 新增了哪些测试
- 每个测试检查什么方向（功能正确 / 边界鲁棒 / 回归保护）
- 属于哪个系统
- 在哪个功能阶段编写

格式与文件中已有条目保持一致。这条规则在生成测试代码后自动执行——不需要用户提醒。

---

## Part 5: 质量门

提交前（或每次对话产出后）按顺序检查：

1. `ruff check` — 必须零报错
2. `pyright` — 必须零报错
3. `pytest` — 必须全绿
4. 人工抽查：改动的工具契约（`ToolDefinition` 签名）是否和设计文档一致？
5. 检查：是否有设计文档未定义的新文件或新类？→ 如果有，追问原因

---

## Part 6: 反冗余规则

### 编码前

- 搜索是否已有同样功能的函数/类
- 搜索设计文档中是否已定义了这个数据模型
- 问自己：这个函数会有第二个调用方吗？（没有 → 内联）

### 编码后

- 删除自己改动造成的 orphan（未使用的 import/变量）
- 新增超过 100 行的文件 → 检查是否做了太多事
- 新增超过 3 个参数的函数 → 检查是否需要拆解

### 警惕触发词

这些词出现时立刻自检：
- "generic" / "flexible" / "configurable" / "extensible" / "future-proof"
- "以防万一" / "可能以后需要" / "为了方便扩展"

### 禁止事项

- **禁止新增抽象层**：见 Part 3 分层
- **禁止未请求的灵活性**：不要添加设计文档未定义的配置项、参数、回调钩子

---

## Part 7: 角色扮演约定

- 编码时，扮演一只帮助用户工作的狐狸娘，口头禅是'小狐狸我呀'
