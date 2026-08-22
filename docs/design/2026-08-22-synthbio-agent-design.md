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
- 任务历史完整落库驱动的天然可回溯（每次运行 plan/steps/report 持久化，可回看每一步）。
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
| FR4 | 步骤实时可视化 |
| FR5 | 任务历史与任意运行回溯 |
| FR6 | 知识检索（RAG）增强规划与回答 |
| FR7 | 环境诊断（R/Python 依赖自检） |

### 非功能需求

| 编号 | 需求 |
|------|------|
| NFR1 | 可扩展性：新增工具只需加一个文件 |
| NFR2 | 可观测性：LangSmith 追踪全链路 |
| NFR3 | 可回溯性：任务完整落库（plan/steps/report），历史可回看 |
| NFR4 | 部署：Docker 一键起全套 |
| NFR5 | 代码质量：ruff / pyright / pytest 零报错 |
| NFR6 | 多 LLM：MVP 用 DeepSeek，接口可换 |

## 4. 架构

### 4.1 分层图

```
┌────────────────────────────────────────────────────────┐
│ 前端  React + Vite + TypeScript                        │
│  聊天界面 / 步骤列表 / 结果图 / 任务历史                 │
│  状态：Zustand stores；流式：hooks/useSSE.ts            │
└───────────────────────┬────────────────────────────────┘
                        │ REST(FastAPI) + SSE
┌───────────────────────┴────────────────────────────────┐
│ 后端  FastAPI                                           │
│  API 层：/chat /tasks /uploads /tools                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Agent 编排层（LangGraph）                         │  │
│  │  router → planner → executor → reporter           │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌─────────────────────┐   │
│  │ 工具注册表  │ │ RAG 层   │ │ 观测（LangSmith）    │   │
│  │ tools/     │ │ RagClient│ │                     │   │
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
│   ├── bioagent/              # Python 包（import 为 bioagent.*）
│   │   ├── main.py            # FastAPI 入口 + 组合根
│   │   ├── api.py             # 路由：chat, tasks, uploads, tools
│   │   ├── enums.py           # Category / Runtime / TaskStatus
│   │   ├── types.py           # ToolDefinition / LLMOutput / EvalReport / TokenUsage
│   │   ├── config.py          # Config + load_config
│   │   ├── db.py              # SQLite 连接 + 迁移
│   │   ├── llm/client.py      # 唯一 LLM 出口（LangChain）
│   │   ├── tools/             # ★ 工具注册表 + 工具定义（加工具放这里）
│   │   │   ├── __init__.py    # ToolRegistry（自动发现）
│   │   │   ├── dge/           # 差异表达（limma）
│   │   │   ├── enrichment/    # 富集（GO/KEGG）
│   │   │   ├── network/       # 网络药理学（PPI/STRING）
│   │   │   ├── single_gene/   # 单基因表达
│   │   │   └── survival/      # 生存分析（KM/Cox）
│   │   ├── r_runner.py        # R 子进程执行器（RRunner）
│   │   ├── rag.py             # Embedder + RagClient（Qdrant）
│   │   ├── eval/              # 两个 judge + 落库
│   │   ├── orchestration/     # LangGraph：state / nodes / graph
│   │   └── r_scripts/         # R 脚本（limma_dge.R / go_kegg.R / km_cox.R）
│   └── tests/                 # tests/test_{系统}/
├── frontend/
│   └── src/
│       ├── components/        # Chat / StepList / ResultChart / TaskHistory / FileUpload
│       ├── charts/            # options.ts + ECharts.tsx
│       ├── hooks/useSSE.ts
│       └── stores/            # 每个系统一个 store
├── docker-compose.yml         # 前端 + 后端 + Qdrant
└── docs/
    ├── specs/                 # 16 份实现 spec
    ├── design/                # 设计文档（本文档）
    └── test-inventory.md      # 测试清单
```

## 5. 组件设计

### 5.1 工具注册表（「加工具 = 加一个文件」的核心）

每个工具是 `backend/bioagent/tools/<category>/<tool_name>/` 下一个文件，内含一个 `ToolDefinition`：

```
name          # 唯一标识，如 "limma_dge"
description   # 给 LLM 看的自然语言说明（何时用、输入输出是什么）
category      # Category 分类标签，用于管线裁剪工具集
runtime       # Runtime.PYTHON | Runtime.R
input_schema  # JSON schema（dict），给 LLM 的参数定义
output_schema # JSON schema（dict），结果结构（前端渲染依据）
r_script      # R 脚本名（仅 R 工具；Python 工具为 None）
frontend      # 结果渲染元数据（dict，如图表类型）
run           # Python 工具执行体（async）；R 工具为 None
```

- 后端启动时扫描 `backend/bioagent/tools/` 目录，用 `pkgutil` 自动发现所有 `ToolDefinition`，构建注册表。
- planner 用 `registry.for_categories()` 按类别拿工具子集拼进 prompt；executor 按 plan 步骤名 `registry.get()` 取工具机械调用，**工具与 agent 完全解耦**。
- 加工具 = 丢一个文件 + 重启（层次 A：启动自动发现）。

工具分类（`category`）与管线裁剪的关系见 5.2。

### 5.2 Agent 编排层（LangGraph StateGraph）

State 字段：

```
query           # 用户问题（贯穿全链）
correlation_id  # 关联 ID（= task id，一次会话的唯一标识）
intent          # router 判定的意图（一句话）
categories      # router 判定的类别（Category.value 列表，管线裁剪依据）
plan            # planner 生成的顺序步骤序列 [{tool, args}]
steps           # executor 每步结果 [{tool, status, result}]（可回溯的数据源）
report          # reporter 生成的最终报告（markdown 纯文本）
```

四个节点：

1. **router**——意图分类，输出 `intent`（一句话意图）+ `categories`（`Category` 值列表，`[c.value for c in Category]` 数据驱动推导）。
2. **planner**——注入 RAG 上下文 + 该管线的工具清单 + 用户需求，用 `json_mode` 一次性生成顺序步骤序列。
3. **executor**——机械执行 planner 产出的步骤（**不调 LLM**）：按 `runtime` 分派 Python `run()` / R `runner`，产出结构化结果。
4. **reporter**——综合步骤结果生成 markdown 报告（纯文本，引用步骤里的数值，图由前端从 steps 取数据画）。

**管线裁剪**：router 判定 `categories` 后，planner 用 `registry.for_categories(categories)` 只拿到该子集内的工具，避免工具清单随工具总数膨胀。

**可回溯**：一次会话 = 一个 task（`correlation_id`），plan/steps/report 完整落库（03-db 的 task 表），SSE 逐节点推前端。可回溯 = 从 task 表读回任意 task 的完整状态。MVP 不接 LangGraph checkpointer（resume 不在范围，见 spec 09）。

**评测锚点（两个 judge）**：工具调用 judge 评的是 **planner 的 `plan`**（`tool_correct` = planner 选的工具是否合适），不是 executor 的 step 输出——executor 机械执行、不选工具；报告 judge 评 reporter 的 `report`。两 judge 按 `judge_sample_rate` 抽样触发（见 08-eval / spec 09 决策 3）。

### 5.3 RAG 层

- `RagClient`（`backend/bioagent/rag.py`）：`Embedder`（本地 sentence-transformers，`all-MiniLM-L6-v2`，dim=384）+ Qdrant（`AsyncQdrantClient`，Docker 独立容器）。
- 知识库：合成生物学 / 生信文档 + 工具使用说明（离线 `ingest` 写入，不在请求路径）。
- 用法：**语料接两处**——planner 规划前、reporter 写报告前各 `rag.query(query)` 取 top_k 相关语料拼进 prompt（`{knowledge}` 占位）；**不作为 executor 的 `knowledge` 工具**。

### 5.4 执行层（Python + R）

- **Python 工具**：`run()` 内直接调用库（pandas / scipy / networkx / httpx 等）。
- **R 工具**：`backend/bioagent/r_runner.py`（`RRunner`）封装 `subprocess` 调 `Rscript`，统一「文件进、文件出」契约：
  - 入：参数（JSON）+ 数据文件路径。
  - 出：结果（JSON）。
  - R 脚本统一放 `backend/bioagent/r_scripts/`。
- 两种工具对外签名一致，编排层无感知差异。

### 5.5 前端

- **聊天界面**：主入口，SSE 流式接收。
- **步骤列表**：SSE 推送状态快照，实时渲染线性步骤（plan 里的步骤 + status），每步结果可展开。
- **结果图展示**：缩放、下载（图由前端从 steps 里各工具 `result` 取数据画，ECharts）。
- **任务历史列表**：从后端读回任意 task 的全部步骤与结果，失败任务显示 `error`。

### 5.6 API 层

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 发起一次运行，返回 SSE 流 |
| `/uploads` | POST | 上传数据文件，返回 `file_id` |
| `/tasks` | GET | 任务历史列表 |
| `/tasks/{task_id}` | GET | 读回单次任务的完整状态 |
| `/tools` | GET | 列出已注册工具（前端展示能力清单） |

## 6. 数据流（一次请求的生命周期）

1. 用户上传表达矩阵 → `/uploads` → 存 `upload_dir`，返回 `file_id`。
2. 用户发消息「对这个表达矩阵做差异表达分析」→ `/chat` → 创建 task（`task_id` = `correlation_id`）。
3. **router**：意图分类 → 输出 `intent` + `categories`（判定 `dge` 管线）。
4. **planner**：注入 RAG 上下文 + `dge` 工具清单 → `json_mode` 生成顺序步骤序列。
5. **executor**：机械执行步骤，调用 `limma_dge`（R 子进程）等工具 → 每步 `{tool, status, result}`。
6. **reporter**：综合步骤结果生成 markdown 报告（纯文本）。
7. 全程每个节点状态经 SSE 推前端渲染步骤列表，终态 plan/steps/report 落 task 表。
8. 用户随时通过 `/tasks/{task_id}` 回看任意历史运行。

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 工具失败（Python 抛错 / R 非零退出） | 异常上抛，10-api 捕获后 task 置 `FAILED` |
| LLM 失败（坏 JSON / 调用失败） | 异常上抛，不重试 |
| RAG 检索失败（Qdrant 未起） | 异常上抛（检索是 planner/reporter 的硬依赖）；collection 为空只返回空列表，不阻断 |
| 观测上报失败（LangSmith） | best-effort，记日志跳过，不影响主流程正确性 |

原则：主流程（LLM / 工具 / RAG）的错误一律异常上抛、task 置 `FAILED`；只有观测上报这类旁路增强允许降级不重抛。

## 8. 测试策略

- **Mock LLM**：所有 LLM 调用点可注入 mock，返回预设 fixture，测试不依赖真实 LLM。
- **Mock R 子进程**：不真跑 Rscript，mock 其 stdout/stderr。
- **每个工具一个测试**：验证「输入走对流程、输出结构正确」，不验 LLM 文本质量。
- **纯计算优先测且测全**（如单基因表达统计 mean/median/sd + t 检验、`Embedder.embed`）。
- **管线测试**：验证 router → … → reporter 的编排正确性（输入走对流程）。
- 测试目录 `tests/test_{系统}/`；每次新增测试后更新 `docs/test-inventory.md`。

## 9. 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React + Vite + TypeScript（strict）+ Zustand + useSSE |
| 后端 | FastAPI + LangChain + LangGraph |
| 多 LLM | LangChain 统一封装，MVP DeepSeek，可换 |
| 向量库 | Qdrant（Docker 独立容器）+ 本地 sentence-transformers embedding |
| 观测 | LangSmith |
| R | subprocess 调 Rscript |
| 数据 | pandas / numpy / scipy / networkx / httpx 等 |
| 部署 | Docker Compose（前端 + 后端 + Qdrant） |
| 质量 | ruff / pyright / pytest |

## 10. MVP 范围与里程碑

### MVP（第一版）

- 框架层：编排 + 注册表 + RAG + 观测 + 前端四件套 + Docker。
- 工具层：**五条管线**所需工具——`dge`（limma 差异表 + 火山图）、`enrichment`（GO/KEGG）、`network`（PPI/STRING）、`single_gene`（表达分布 + t 检验）、`survival`（KM/Cox）。

### 后续里程碑

1. 框架 + 单基因管线跑通（最小闭环验证「加工具」机制）。
2. 转录组差异分析管线（验证 R 集成 + 多工具串联）。
3. 网络药理学管线（验证外部数据库获取）。
4. 补全其余工具（机器学习、单细胞、空间转录组、虚拟扰动、文献检索）。

## 11. 已决策 / 待实现

- embedding 选型：已定本地 `all-MiniLM-L6-v2`（dim=384，见 07-rag）。
- LLM 结构化输出：已定 `json_mode`（router / planner 均 `json_mode=True`，见 09）。
- 数据文件在 Docker 内的持久化策略（volume 挂载 `config.storage.upload_dir`）：实现阶段定。
- R 依赖包的 Docker 镜像分层策略（缩短构建时间）：实现阶段定。
