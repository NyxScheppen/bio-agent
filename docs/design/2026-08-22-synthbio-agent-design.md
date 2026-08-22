# 合成生物学辅助 Agent — 设计文档

- 日期：2026-08-22
- 状态：待审阅
- 目标读者：开发者（我）、未来协作者、面试官

## 1. 概述

一个面向**合成生物学 / 生物信息学**的多 agent 助手：用户用自然语言描述分析需求，agent 自动规划并执行一条分析管线（差异表达、富集、网络药理学、单基因、生存分析……），全程**步骤可视化**、**可回溯**。

项目双重定位：

1. **iGEM 参赛项目**——辅助队伍完成真实的生物数据分析。
2. **AI Agent 求职作品集**——展示清晰的 multiagent 架构、干净的扩展机制、生产级工程实践。

作品集核心卖点（也是本设计的取舍依据）：

- 清晰的 multiagent 编排（router → planner → executor → reporter），而非「一个 prompt 大杂烩」。
- 干净的「加工具 = 加一个文件」扩展机制，工具与 agent 完全解耦。
- LangGraph checkpoint 驱动的天然可回溯。
- Python + R 双语言集成（生物信息学领域的真实需求）。
- 生产级工程实践：Mock 测试、类型检查、观测（LangSmith）、Docker 一键部署。

## 2. 目标与非目标

### 目标

- 多任务执行：覆盖转录组、单基因、网络药理学、生存分析、富集、机器学习、单细胞、空间转录组、虚拟扰动、文献检索、环境诊断等。
- 步骤可视化 + 可回溯：任意一次运行的每一步都能回看。
- 合成生物学知识专家：RAG 增强。
- 可扩展：新增分析能力只加工具代码，不动编排层。

### 非目标（MVP 明确不做）

- **agent 自造工具**（code-interpreter 式运行时生成新工具）——安全风险大、测试负担重，偏离「加工具=加代码」主线。
- **云端多租户 / 鉴权 / 计费**——本地 + Docker 部署，单用户。
- **热加载免重启**（动态 skill 层次 B）——MVP 只做启动自动发现（层次 A）。
- **真实并发任务队列**（Celery / Redis）——MVP 单任务即可，不做超长任务并发。

## 3. 需求

### 功能需求

| 编号 | 需求 |
|------|------|
| FR1 | 自然语言对话入口，理解用户分析意图 |
| FR2 | 文件上传（表达矩阵、临床数据等） |
| FR3 | 执行分析管线并产出结果图与结论 |
| FR4 | 步骤 DAG 实时可视化 |
| FR5 | 任务历史与任意运行回溯 |
| FR6 | 知识检索（RAG）增强规划与回答 |
| FR7 | 环境诊断（R/Python 依赖自检） |

### 非功能需求

| 编号 | 需求 |
|------|------|
| NFR1 | 可扩展性：新增工具只需加一个文件 |
| NFR2 | 可观测性：LangSmith 追踪全链路 |
| NFR3 | 可回溯性：checkpoint 持久化每个节点状态 |
| NFR4 | 部署：Docker 一键起全套 |
| NFR5 | 代码质量：ruff / pyright / pytest 零报错 |
| NFR6 | 多 LLM：MVP 用 DeepSeek，接口可换 |

## 4. 架构

### 4.1 分层图

```
┌────────────────────────────────────────────────────────┐
│ 前端  React + Vite + TypeScript                        │
│  聊天界面 / 步骤DAG / 结果图 / 任务历史                  │
│  状态：Zustand stores；流式：hooks/useSSE.ts            │
└───────────────────────┬────────────────────────────────┘
                        │ REST(FastAPI) + SSE
┌───────────────────────┴────────────────────────────────┐
│ 后端  FastAPI                                           │
│  API 层：/chat /tasks /upload /tools /jobs              │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Agent 编排层（LangGraph）                         │  │
│  │  router → planner → executor → reporter           │  │
│  │  + checkpointer（SQLite）                          │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌─────────────────────┐   │
│  │ 工具注册表  │ │ RAG 层   │ │ 观测（LangSmith）    │   │
│  │ tools/     │ │ Retriever│ │                     │   │
│  │ 自动发现    │ │ → Qdrant │ │                     │   │
│  └────────────┘ └──────────┘ └─────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 执行层：Python 工具 + R 子进程（Rscript）         │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### 4.2 目录结构

```
bio-agent/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── api/               # 路由：chat, tasks, upload, tools, jobs
│   │   ├── agents/            # LangGraph：router, planner, executor, reporter
│   │   ├── registry/          # 工具注册表（自动发现）
│   │   ├── rag/               # retriever 接口 + qdrant 实现
│   │   ├── runners/           # Python / R 执行器
│   │   └── schemas/           # Pydantic 模型
│   ├── tools/                 # ★ 工具定义（加工具放这里）
│   │   ├── dge/               # 差异表达
│   │   ├── enrichment/        # 富集
│   │   ├── network/           # 网络药理学
│   │   ├── single_gene/       # 单基因
│   │   ├── survival/          # 生存分析
│   │   └── ...                # 后续按 category 增加
│   ├── r_scripts/             # R 脚本（被 R 工具调用）
│   └── tests/                 # tests/test_{系统}/
├── frontend/
│   └── src/
│       ├── components/        # Chat / StepDAG / ResultFigure / TaskHistory
│       ├── hooks/useSSE.ts
│       └── stores/            # 每个系统一个 store
├── docker-compose.yml         # 前端 + 后端 + Qdrant
└── docs/
    ├── specs/                 # 设计文档（本文档）
    └── test-inventory.md      # 测试清单
```

## 5. 组件设计

### 5.1 工具注册表（「加工具 = 加一个文件」的核心）

每个工具是 `backend/tools/<category>/<tool_name>/` 下一个文件，内含一个 `ToolDefinition`：

```
name          # 唯一标识，如 "deseq2_diff_expr"
description   # 给 LLM 看的自然语言说明（何时用、输入输出是什么）
category      # 分类标签，用于管线裁剪工具集
runtime       # "python" | "r"
input_schema  # Pydantic 模型，参数校验
output_schema # Pydantic 模型，结构化返回
frontend      # 结果渲染元数据（图表类型、卡片标题）
async def run(**input_schema) -> output_schema   # 执行函数
```

- 后端启动时扫描 `tools/` 目录，用 `importlib` 自动发现所有 `ToolDefinition`，构建注册表。
- executor 每次运行时从注册表动态生成 LangChain tool 列表，**工具与 agent 完全解耦**。
- 加工具 = 丢一个文件 + 重启（层次 A：启动自动发现）。

工具分类（`category`）与管线裁剪的关系见 5.2。

### 5.2 Agent 编排层（LangGraph StateGraph）

State 字段：

```
messages        # 对话历史
intent          # router 判定的意图
plan            # planner 生成的步骤计划
steps           # 已执行步骤及其结果（可回溯的数据源）
report          # reporter 生成的最终报告
```

四个节点：

1. **router**——意图分类，判定用户属于哪条管线（`dge` / `single_gene` / `network` / `system` / 闲聊兜底）。
2. **planner**——动态 prompt：注入 RAG 上下文 + 该管线的工具清单 + 用户需求，生成步骤计划。
3. **executor**——agentic tool-calling 循环，绑定**该管线裁剪后的工具子集**，产出结构化结果。
4. **reporter**——综合结果生成报告，引用产出的图。

**管线裁剪**：每个 `category` 对应一条管线，router 判定意图后，executor 只绑定该类别（+ 通用类别 `data` / `knowledge` / `system`）的工具子集，避免 tool 列表随工具总数膨胀。

**checkpointer**：SQLite（后续可换 Postgres）持久化每个节点状态，`thread_id` 标识一次运行。可回溯 = 从 checkpointer 读回任意 `thread_id` 的完整状态。

### 5.3 RAG 层

- `Retriever` 接口（薄抽象）：`async retrieve(query, top_k) -> list[Document]`。
- Qdrant 实现（生产/一键部署用）；本地开发可用 Chroma 实现，二者共用同一接口。
- 知识库：合成生物学 / 生信文档 + 工具使用说明。
- 两种用法：① 作为 `knowledge` 工具被 executor 调用；② 注入 planner/reporter 的上下文。
- embedding 模型 MVP 用 DeepSeek 或本地模型，实现计划阶段再定。

> 说明：`Retriever` 接口是合理的边界（retriever 依赖接口而非具体向量库），不是「以防万一」的过度抽象——这是 RAG 层与具体存储之间的天然接缝。

### 5.4 执行层（Python + R）

- **Python 工具**：`run()` 内直接调用库（pandas / scikit-learn / gseapy 等）。
- **R 工具**：`runners/` 封装 `subprocess` 调 `Rscript`，统一「文件进、文件出」契约：
  - 入：参数（JSON）+ 数据文件路径。
  - 出：结果（CSV / JSON）+ 图（PNG）。
  - R 脚本统一放 `backend/r_scripts/`。
- 两种工具对外签名一致，编排层无感知差异。

### 5.5 前端

- **聊天界面**：主入口，SSE 流式接收。
- **步骤 DAG**：SSE 推送节点状态，实时渲染 router → planner → executor → reporter，每步输入 / 输出 / 状态可展开。
- **结果图展示**：缩放、下载。
- **任务历史列表**：从后端读回任意 `thread_id` 的全部步骤与结果。

### 5.6 API 层

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 发起 / 续接一次运行，返回 SSE 流 |
| `/upload` | POST | 上传数据文件，返回 `file_id` |
| `/tasks` | GET | 任务历史列表 |
| `/tasks/{thread_id}` | GET | 读回单次运行的完整状态 |
| `/tools` | GET | 列出已注册工具（前端展示能力清单） |
| `/jobs` | GET | 环境诊断 / 运行状态 |

## 6. 数据流（一次请求的生命周期）

1. 用户上传表达矩阵 → `/upload` → 存临时目录，返回 `file_id`。
2. 用户发消息「对这个表达矩阵做差异表达分析」→ `/chat` → 创建 LangGraph 线程（`thread_id`）。
3. **router**：意图分类 → 判定 `dge` 管线。
4. **planner**：注入 RAG 上下文 + `dge` 工具清单 → 生成步骤计划。
5. **executor**：tool-calling 循环，调用 `deseq2_diff_expr`（R 子进程）等工具 → 结果。
6. **reporter**：综合生成报告 + 图表引用。
7. 全程每个节点状态经 checkpointer 持久化，同时 SSE 推前端渲染 DAG。
8. 用户随时通过 `/tasks/{thread_id}` 回看任意历史运行。

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 工具失败 | 捕获 → 记录到 `steps` → executor 决定重试 / 换工具 / 上报，不中断整条管线 |
| LLM 失败 | 重试 + 降级默认值 |
| R 子进程失败 | 捕获 stderr，结构化返回给 executor |
| 旁路系统失败（RAG 检索 / 观测上报） | best-effort，记日志返默认值，不影响主流程正确性 |

原则：主流程（分析管线）的错误必须显式处理；旁路增强（RAG、观测）的失败允许降级不重抛。

## 8. 测试策略

- **Mock LLM**：所有 LLM 调用点可注入 mock，返回预设 fixture，测试不依赖真实 LLM。
- **Mock R 子进程**：不真跑 Rscript，mock 其 stdout/stderr。
- **每个工具一个测试**：验证「输入走对流程、输出结构正确」，不验 LLM 文本质量。
- **纯计算函数测全**（KM 估计、PCA、富集统计等纯函数优先且测全）。
- **管线测试**：验证 router → … → reporter 的编排正确性（输入走对流程）。
- 测试目录 `tests/test_{系统}/`；每次新增测试后更新 `docs/test-inventory.md`。

## 9. 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React + Vite + TypeScript（strict）+ Zustand + useSSE |
| 后端 | FastAPI + LangChain + LangGraph |
| 多 LLM | LangChain 统一封装，MVP DeepSeek，可换 |
| 向量库 | Qdrant（本地开发可换 Chroma） |
| 观测 | LangSmith |
| R | subprocess 调 Rscript |
| 数据 | pandas / numpy / scikit-learn / gseapy 等 |
| 部署 | Docker Compose（前端 + 后端 + Qdrant） |
| 质量 | ruff / pyright / pytest |

## 10. MVP 范围与里程碑

### MVP（第一版）

- 框架层：编排 + 注册表 + RAG + 观测 + 前端四件套 + Docker。
- 工具层：**三条示范管线**所需工具——`dge`（DESeq2/limma + PCA + 火山图）、`enrichment`（GO/KEGG）、`network`（PPI/STRING）、`single_gene`（表达 + 相关性 + 生存）、`survival`（KM/Cox/LASSO）。
- 通用工具：`data`（上传/读取）、`knowledge`（RAG）、`system`（环境诊断）。

### 后续里程碑

1. 框架 + 单基因管线跑通（最小闭环验证「加工具」机制）。
2. 转录组差异分析管线（验证 R 集成 + 多工具串联）。
3. 网络药理学管线（验证外部数据库获取）。
4. 补全其余工具（机器学习、单细胞、空间转录组、虚拟扰动、文献检索）。

## 11. 开放问题（实现计划阶段解决）

- embedding 模型具体选型（DeepSeek embedding vs 本地模型）。
- LLM 结构化输出（router 意图、工具参数）用 JSON mode 还是 function calling。
- 数据文件在 Docker 内的持久化策略（volume 挂载临时目录）。
- R 依赖包的 Docker 镜像分层策略（缩短构建时间）。
