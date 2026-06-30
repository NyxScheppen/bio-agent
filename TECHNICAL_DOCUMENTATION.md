# BioAI Agent 技术文档

> **版本**: 2.0  
> **最后更新**: 2026-06-27  
> **项目类型**: 生物信息学与合成生物学 AI Agent 全栈应用

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [技术栈](#3-技术栈)
4. [目录结构](#4-目录结构)
5. [后端架构详解](#5-后端架构详解)
6. [Multi-Agent 流水线](#6-multi-agent-流水线)
7. [工具系统](#7-工具系统)
8. [Skill 技能系统](#8-skill-技能系统)
9. [工具执行 Harness](#9-工具执行-harness)
10. [R 集成方案](#10-r-集成方案)
11. [数据库设计](#11-数据库设计)
12. [API 接口](#12-api-接口)
13. [前端架构](#13-前端架构)
14. [会话与上下文管理](#14-会话与上下文管理)
15. [规则、Hooks 与命令](#15-规则hooks-与命令)
16. [特性开关](#16-特性开关)
17. [部署与运维](#17-部署与运维)
18. [开发指南](#18-开发指南)

---

## 1. 项目概述

BioAI Agent 是一个面向生物信息学与合成生物学领域的 AI 智能助手。用户可以通过自然语言对话上传生物数据文件，执行生存分析、转录组分析、富集分析、机器学习建模、网络药理学分析、单细胞分析、空间转录组分析等专业生信任务。

**核心特性**：
- **Multi-Agent 架构**：Router → Skill Select → Planner → [Delegator] → Executor → Reporter 流水线
- **并行工具执行**：依赖感知并行 + Waterfall Racing 竞速模式
- **54 个 Skill**：YAML/SKILL.md 驱动的任务专精技能包，覆盖 16 个生信类别
- **子Agent 委派**：Kanban 编排器，复杂任务自动拆分为并行子Agent
- **45+ 专业生信工具**：覆盖 16 个生物信息学工具类别
- **R 深度集成**：通过子进程调用 Rscript，内置私有 R 包库管理
- **Session Memory**：支持跨轮次会话记忆和短回复解析
- **统一工具生命周期**：ToolResult 协议 + 资源限制 + 审计日志 + 恢复策略
- **结构化规则引擎**：22 条规则按 Agent 角色和类别动态激活
- **Hook 系统**：4 个生命周期钩子点，支持事件驱动自动化
- **斜杠命令**：19 个快捷命令（`/survival`、`/deg`、`/enrich` 等）
- **循环护栏**：空转检测 + 熔断器 + 6 种自动恢复策略
- **自改进反馈**：失败模式记录 → 分析 → 改进建议

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                       前端 (SPA)                              │
│                  Vite + React (Static)                        │
│               backend/static/index.html                       │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP / WebSocket
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI 后端                                │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌────────────┐ │
│  │ API 层  │  │ 服务层   │  │ Agent 层   │  │ 工具层     │ │
│  │ chat    │  │ chat     │  │ Router     │  │ survival   │ │
│  │ upload  │  │ session  │  │ Planner    │  │ transcript │ │
│  │ history │  │ file     │  │ Delegator  │  │ enrichment │ │
│  │ system  │  │ system   │  │ Executor   │  │ ml ...     │ │
│  └─────────┘  └──────────┘  │ Reporter   │  │  45+ tools │ │
│                             │ Skill 系统 │  └────────────┘ │
│                             │ Sub-Agent  │                 │
│                             │ Orchestr.  │                 │
│                             └────────────┘                 │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              基础设施层                                   ││
│  │  SQLite DB    │  Session Memory  │  R Subprocess  │     ││
│  │  Audit Logs   │  Context Manager │  DeepSeek API  │     ││
│  │  Resource Mon │  Recovery Strat  │  Rules Engine  │     ││
│  │  Hook Manager │  Command Parser  │  Skill Improver│     ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 请求流程

```
用户输入
  → chat_service.handle_chat()
    → 上下文压缩 (maybe_compact_context)
    → Session Memory 注入 (enrich_context_with_session_memory)
    → 短回复解析 (resolve_short_user_reply)
    → run_bio_agent()
      → [命令解析] 斜杠命令直接映射 Skill
      → Router Agent: 任务分类
      → Skill 选择: 匹配技能包 (54 Skills)
      → Planner Agent: 制定执行计划 (+ parallel_groups)
      → [Delegator Agent]: 复杂任务拆分子Agent
      → Executor Agent: 并行/串行/竞速工具调用
        → Hook 触发 (pre/post tool)
        → 资源限制 (timeout/memory/CPU)
        → 恢复策略 (6 strategies)
        → 空转检测 + 熔断器
        → 审计日志写入
      → Reporter Agent: 生成最终回复
    → 文件合并 & 去重
    → 保存数据库记录
  → 返回 { reply, files }
```

---

## 3. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI 0.135+ | 异步 Python Web 框架 |
| **ASGI 服务器** | Uvicorn 0.44 | 轻量级 ASGI 服务器 |
| **AI/LLM** | DeepSeek API (OpenAI SDK) | 通过 OpenAI 兼容客户端调用 |
| **数据库** | SQLite + SQLAlchemy 2.0 | ORM + 单文件本地数据库 |
| **R 集成** | subprocess + Rscript | 子进程调用 R 进行生信分析 |
| **R 包管理** | 私有 env/r_libs 目录 | 隔离的 R 私有包库 |
| **前端** | Vite + React (SPA) | 打包为静态文件由 FastAPI 托管 |
| **数据科学** | Pandas, NumPy, Scikit-learn, SciPy | Python 数据处理 |
| **可视化** | Matplotlib, Seaborn (Python), ggplot2 (R) | 图表生成 |
| **数据验证** | Pydantic 2.x | 请求/响应模型校验 |
| **运行环境** | Python 3.10-3.12, R 4.2+ | 双语言运行时 |
| **平台** | Windows (主), 兼容 Linux | 跨平台设计 |

---

## 4. 目录结构

```
bio_test/
├── start_app.bat              # 一键启动脚本（Windows）
├── check_env.bat              # 环境检测脚本
├── build_portable.bat         # 便携版构建脚本
├── requirements.txt           # Python 依赖列表
├── install_r_packages.R       # R 包安装脚本
├── TECHNICAL_DOCUMENTATION.md # 本文档
│
├── backend/                   # 后端根目录
│   ├── .env                   # 环境变量（API Key、端口等）
│   ├── static/                # 前端静态文件 (Vite build)
│   │   ├── index.html
│   │   └── assets/
│   ├── storage/               # 文件存储根目录（运行时）
│   │   ├── uploads/           # 用户上传文件
│   │   ├── generated/         # 分析生成文件
│   │   └── temp/              # 临时文件
│   ├── db_data/               # SQLite 数据库文件
│   └── app/
│       ├── main.py            # FastAPI 入口
│       ├── api/               # API 路由层
│       │   ├── chat.py        # 聊天接口 + 会话删除
│       │   ├── upload.py      # 文件上传/列表/删除
│       │   ├── history.py     # 会话历史查询
│       │   └── system.py      # 系统信息接口
│       ├── agent/             # Multi-Agent 核心
│       │   ├── bio_agent.py   # Agent 主入口
│       │   ├── router_agent.py    # Router: 任务分类 + 命令解析
│       │   ├── planner_agent.py   # Planner: 制定计划
│       │   ├── delegator_agent.py # Delegator: 子Agent委派 (Phase 3)
│       │   ├── executor_agent.py  # Executor: 并行/串行/竞速 + 护栏
│       │   ├── reporter_agent.py  # Reporter: 生成报告
│       │   ├── parallel_executor.py   # 依赖感知并行执行 (Phase 1)
│       │   ├── racing_executor.py     # Waterfall Racing 竞速 (Phase 1)
│       │   ├── sub_agent_manager.py   # 子Agent管理器 (Phase 3)
│       │   ├── orchestrator.py        # Kanban 多Agent编排 (Phase 3)
│       │   ├── category_router.py # 工具类别路由
│       │   ├── context_manager.py # 会话上下文管理
│       │   ├── llm_client.py      # LLM API 客户端
│       │   ├── task_prompts.py    # Agent 提示词模板 (含 RulesEngine 集成)
│       │   ├── rules_engine.py    # 结构化规则引擎 (Phase 5)
│       │   ├── hooks.py           # Hook 系统 (Phase 5)
│       │   ├── commands.py        # 斜杠命令 (Phase 5)
│       │   ├── tool_registry.py   # 工具注册中心 (含 racing_group)
│       │   ├── tool_result.py     # 标准工具返回协议 (含 ResourceUsage/RetryRecord)
│       │   ├── tool_runner.py     # 工具生命周期包装器 (含 ResourceMonitor/Hooks/Audit)
│       │   ├── tool_context.py    # 工具执行上下文
│       │   ├── tool_discovery.py  # 工具自动发现
│       │   ├── recovery_strategies.py # 恢复策略 (6 strategies)
│       │   ├── skill_improver.py  # 自改进反馈 (Phase 4)
│       │   ├── agent_utils.py     # Agent 工具函数
│       │   ├── agent_constants.py # 常量 + FEATURE_FLAGS
│       │   └── skills/            # Skill 技能系统
│       │       ├── skill_models.py    # Skill 数据模型
│       │       ├── skill_registry.py  # Skill 注册表
│       │       ├── skill_loader.py    # YAML + SKILL.md 加载器
│       │       ├── skill_router.py    # Skill 匹配选择
│       │       ├── skill_export.py    # Skill 导出 (Phase 2)
│       │       ├── builtin_skills.py  # 内置技能定义
│       │       └── packs/             # Skill 定义 (18 YAML packs)
│       │           ├── survival.yaml, transcriptome.yaml, ...
│       │           ├── single_gene.yaml, advanced_bio.yaml, ml_advanced.yaml
│       ├── tools/              # 生信分析工具集
│       │   ├── __init__.py         # 工具模块注册
│       │   ├── basic_tools.py      # 基础生信工具
│       │   ├── file_tools.py       # 文件读写工具
│       │   ├── r_tools.py          # R 执行工具
│       │   ├── r_preprocess_templates.py # R 预处理模板
│       │   ├── system_tools.py     # 系统环境扫描
│       │   ├── literature_tools.py # 文献检索工具
│       │   ├── single_gene_tools.py    # 单基因分析
│       │   ├── survival_tools.py       # 生存分析
│       │   ├── transcriptome_tools.py  # 转录组分析
│       │   ├── enrichment_tools.py     # 富集分析
│       │   ├── ml_tools.py             # 机器学习
│       │   ├── network_pharmacology_tools.py # 网络药理学
│       │   ├── perturbation_tools.py   # 虚拟扰动
│       │   ├── scrna_tools.py          # 单细胞分析
│       │   └── spatial_tools.py        # 空间转录组
│       ├── services/           # 业务服务层
│       │   ├── chat_service.py     # 聊天总控
│       │   ├── session_service.py  # 会话管理
│       │   ├── file_service.py     # 文件管理
│       │   └── system_service.py   # 系统信息服务
│       ├── db/                 # 数据库层
│       │   ├── database.py     # 连接配置
│       │   ├── models.py       # ORM 模型 (含 ToolExecution)
│       │   ├── crud.py         # CRUD 操作 (含审计日志)
│       │   └── audit.py        # 非阻塞审计写入 (Feature 2)
│       ├── schemas/            # Pydantic 请求/响应模型
│       │   ├── chat.py         # 聊天请求模型
│       │   └── file.py         # 文件模型
│       ├── core/               # 核心配置
│       │   ├── config.py       # 环境变量配置
│       │   ├── paths.py        # 路径管理（legacy）
│       │   └── runtime_paths.py # 运行时路径 + Rscript 定位
│       └── utils/              # 工具函数
│           ├── file_utils.py
│           ├── file_resolver.py    # 文件路径解析
│           └── response_formatter.py # 回复格式化
│
├── env/                       # 运行环境
│   └── r_libs/                # R 私有包库
│
├── runtime/                   # 运行时文件（启动脚本等）
├── logs/                      # 日志目录
└── docs/                      # 开发文档
    ├── tool_result_standard.md    # ToolResult 协议文档
    ├── tool_lifecycle.md          # 工具生命周期文档
    └── tool_registration.md       # 工具注册文档
```

---

## 5. 后端架构详解

### 5.1 FastAPI 应用入口 (`main.py`)

- **静态文件服务**：FastAPI 直接托管 Vite 构建产物
- **SPA 路由兜底**：未匹配 API 路由的请求返回 `index.html`
- **CORS 全开放**：开发阶段允许所有来源跨域
- **自动建表**：启动时执行 `Base.metadata.create_all()`
- **路由注册**：
  - `/api/chat` — 聊天接口
  - `/api/upload` — 文件上传
  - `/api/uploads/{session_id}` — 文件列表
  - `/api/history` — 会话历史
  - `/api/system-info` — 系统信息
  - `/api/health` — 健康检查
  - `/files/` — 静态文件服务（uploads + generated）

### 5.2 配置管理 (`core/config.py`)

通过 `python-dotenv` 从 `backend/.env` 加载：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 端点 |
| `MODEL_NAME` | `deepseek-chat` | 模型名称 |
| `API_HOST` | `127.0.0.1` | 监听地址 |
| `API_PORT` | `8000` | 监听端口 |

### 5.3 路径管理 (`core/runtime_paths.py`)

核心功能：
- **Rscript 自动定位**：按优先级扫描环境变量、项目内置、PATH、注册表（Windows）、常见安装路径
- **跨平台支持**：Windows 注册表查找 + Linux 路径兜底
- **R 子进程环境构建**：注入 `R_LIBS_USER`、`PROJECT_ROOT`、`UPLOAD_DIR`、`GENERATED_DIR` 等环境变量

---

## 6. Multi-Agent 流水线

### 6.1 概述

Agent 系统采用 **Router → Skill Select → Planner → [Delegator] → Executor → Reporter** 流水线：

```
用户输入 + 上下文
      │
      ▼
┌──────────────┐
│  命令解析    │  斜杠命令直接映射 Skill，跳过 LLM
│  (Phase 5)   │  e.g. /survival → single_gene_survival
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Router     │  判断任务类型、复杂度和所需工具类别
│   Agent      │  输出 JSON: { task_type, complexity, tool_categories, ... }
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Skill Select │  从 54 个 Skill 中匹配 (trigger_keywords + task_type)
│              │  匹配失败 → free-planning fallback
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Planner    │  制定执行计划，可标注 parallel_groups
│   Agent      │  输出 JSON: { steps, parallel_groups, max_tool_rounds, ... }
└──────┬───────┘
       │
       ▼ (complexity=="complex" 时)
┌──────────────┐
│  Delegator   │  判断是否拆分子Agent 并行执行
│  (Phase 3)   │  输出 JSON: { should_delegate, sub_tasks, ... }
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Executor    │  串行/并行/竞速调用工具，护栏保护
│   Agent      │  ResourceMonitor + RecoveryStrategies + 空转检测 + 熔断器
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Reporter    │  汇总全部结果 + Skill 报告模板
│   Agent      │  生成结构化中文报告 + Markdown 图片/下载链接
└──────┬───────┘
       │
       ▼
   最终回复 + 文件列表
```

### 6.2 各 Agent 详解

#### Router Agent (`router_agent.py`)

- **职责**：判断用户请求类型，不执行任务
- **输入**：上下文摘要 + 最近消息 + 最新用户消息
- **输出**：
  - `task_type`：`bioinformatics | modeling | drug_screening | literature | file_processing | system | general | unclear`
  - `complexity`：`simple | medium | complex`
  - `suggested_mode`：`direct_answer | tool_execution | ask_user`
  - `tool_categories`：如 `["survival", "file_io"]`
  - `risk_flags`：如 `["缺少time/status"]`
- **模式**：严格 JSON 输出，temperature=0

#### Planner Agent (`planner_agent.py`)

- **职责**：制定详细执行计划，考虑 Skill 约束和 workflow_policy
- **输入**：Router 结果 + 可用工具列表 + Skill 定义
- **输出**：
  - `execution_mode`：`answer_only | tool_execution | ask_user`
  - `steps`：每个步骤的目标、工具、参数策略、成功标准
  - `max_tool_rounds`：最大工具调用轮次
- **Workflow Policy**：根据工具类别注入特定工作流规则（如生存分析先确认 time/status）

#### Executor Agent (`executor_agent.py`)

- **职责**：按计划调用工具，处理错误，自动恢复
- **执行模式**：
  - **串行**（默认）：for-loop 逐轮调用 LLM + 工具
  - **并行**（opt-in）：Planner 输出 `parallel_groups` 时，拓扑排序后 ThreadPoolExecutor 并发
  - **竞速**（opt-in）：同 `racing_group` 的多个工具同时启动，取第一个成功
- **护栏机制**：
  - **空转检测**：同工具+同参数重复 ≥3 次 → 强制终止
  - **熔断器**：连续 3 个错误 → 停止执行
  - **致命错误检测**：参数签名错误、不存在的工具等 → 立即停止
  - **自动恢复**：6 种 RecoveryStrategy 自动诊断和修复
- **资源限制**：ResourceMonitor（psutil）+ ThreadPoolExecutor timeout
- **审计日志**：每次工具调用自动写入 `tool_executions` 表
- **自改进**：失败模式自动记录到 `skill_improver`

#### Reporter Agent (`reporter_agent.py`)

- **职责**：整理最终用户回复
- **输入**：Router + Planner + Executor 全部结果 + Skill 报告模板
- **输出**：结构化中文报告（完成情况 → 关键结果 → 生成文件 → 下一步建议）
- **安全检查**：`remove_fake_markdown_images()` 拦截不存在的图片引用

### 6.3 执行模式

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| `ask_user` | 缺少关键输入（文件/列名/参数） | 生成追问问题，不执行工具 |
| `answer_only` | 简单问答、不需要工具 | 直接通过 Reporter 生成回答 |
| `tool_execution` | 需要实际分析/计算 | 完整走 Executor 多轮工具调用 |

---

## 7. 工具系统

### 7.1 工具注册

工具通过 `@register_tool()` 装饰器注册到全局 `TOOL_REGISTRY`，支持三种模式：

**模式 1：手动 Schema（兼容旧代码）**
```python
@register_tool(
    name="calculate_gc_content",
    description="计算 DNA 序列 GC 含量",
    parameters={...},  # 手写 OpenAI function schema
    category="basic",
)
def calculate_gc_content(sequence: str): ...
```

**模式 2：Pydantic 模型**
```python
class MyParams(BaseModel):
    gene: str = Field(description="基因名")
    threshold: float = Field(default=0.05)

@register_tool(
    name="my_analysis",
    description="基因分析",
    params_model=MyParams,
    category="survival",
)
def my_analysis(gene: str, threshold: float = 0.05): ...
```

**模式 3：函数签名自动推导**
```python
@register_tool(
    name="count_bases",
    description="计数碱基",
    category="basic",
)
def count_bases(sequence: str, include_gaps: bool = False): ...
```

### 7.2 工具分类体系

| 类别 | 说明 | 代表工具 |
|------|------|---------|
| `file_io` | 文件读写/预览/探测 | `preview_table_file`, `read_csv_data`, `probe_unknown_file` |
| `basic` | 基础序列计算 | `calculate_gc_content` |
| `literature` | 文献检索 | `search_literature`, `fetch_paper_details` |
| `single_gene` | 单基因分析 | `run_single_gene_survival_analysis` |
| `survival` | 生存分析与预后模型 | `run_lasso_cox_model`, `run_prognostic_risk_model` |
| `transcriptome` | Bulk RNA-seq / 差异表达 | `run_bulk_rnaseq_deg_analysis`, `run_deseq2_count_deg_analysis` |
| `enrichment` | GO/KEGG/GSEA/GSVA 富集 | `run_enrichment_analysis` |
| `ml` | 机器学习分类/特征选择 | `run_ml_classification`, `run_lasso_feature_selection` |
| `network_pharmacology` | 网络药理学/PPI | `run_network_pharmacology_analysis` |
| `perturbation` | 虚拟敲低/扰动 | `run_virtual_knockdown` |
| `scrna` | 单细胞分析 | Seurat 相关工具 |
| `spatial` | 空间转录组 | 空间分析工具 |
| `modeling` | 分子建模/对接 | 蛋白结构分析工具 |
| `drug_screening` | 药物筛选 | 候选药物筛选工具 |
| `aptamer` | 适配体筛选 | 适配体分析工具 |
| `system` | 系统环境诊断 | `scan_system_config` |

### 7.3 工具生命周期

每次工具调用经过 `run_tool_with_lifecycle()` 包装器：

```
创建 ToolExecutionContext（自动 job_id / job_dir）
    ↓
注入 runtime 参数（session_id, job_dir, context）
    ↓
执行工具函数
    ↓
捕获异常 → 构造 error ToolResult
    ↓
归一化为标准 ToolResult
    ↓
自动扫描 job_dir 中生成文件
    ↓
合并 output_files（显式 + 自动收集）
    ↓
填充 provenance（参数、时间、runtime 等）
    ↓
返回标准 ToolResult
```

### 7.4 ToolResult 标准协议

所有工具返回统一格式（Pydantic 模型）：

```python
class ToolResult(BaseModel):
    status: str          # "success" | "error" | "partial"
    message: str         # 人类可读描述
    summary: Dict        # 结构化摘要（统计数字等）
    tables: List[ResultTable]
    figures: List[ResultFigure]
    output_files: List[OutputFile]  # 前端据此展示文件
    warnings: List[str]
    errors: List[str]
    provenance: ToolProvenance      # 执行溯源
```

---

## 8. Skill 技能系统

### 8.1 概述

Skill 是比单个工具更高层的任务能力包，封装了某类生信任务的完整元信息：
- **何时触发**：task_type / subtask_type / trigger_keywords 匹配
- **需要什么输入**：required_inputs / optional_inputs
- **用什么工具**：allowed_tools 白名单 / banned_tools 黑名单
- **参数如何填**：parameter_rules（from_file_preview / from_user / auto_detect / default）
- **何时追问**：clarification_rules
- **报告怎么组织**：report_sections 章节模板

### 8.2 Skill 匹配流程

```
Router 结果
    ↓
select_skill(latest_user_message, router_result)
    ↓
1. 按 task_type + subtask_type 精确匹配
2. 按 task_type 匹配
3. 按 subtask_type 匹配
4. 按 trigger_keywords 匹配
    ↓
返回 SkillSpec 或 None (free-planning)
```

### 8.3 内置 Skills (54 个, 19 implemented)

Skills 从 `skills/packs/` 下 18 个 YAML 文件加载，也支持 SKILL.md 格式。

**已实现的核心 Skills**：

| Skill ID | 名称 | 类别 | 轮次 |
|----------|------|------|------|
| `file_probe` | 文件探测与预览 | file_io | 4 |
| `geo_data_download` | GEO 数据下载 | file_io | 6 |
| `single_gene_survival` | 单基因生存分析 | survival | 10 |
| `univariate_cox_batch` | 批量单因素 Cox | survival | 10 |
| `lasso_cox_model` | LASSO-Cox 预后模型 | survival | 14 |
| `prognostic_risk_model` | 预后风险评分模型 | survival | 14 |
| `bulk_rnaseq_deg` | Bulk RNA-seq 差异分析 | transcriptome | 14 |
| `deseq2_count_deg` | DESeq2 差异分析 | transcriptome | 14 |
| `bulk_pca_analysis` | PCA 分析 | transcriptome | 6 |
| `go_enrichment` | GO 富集分析 | enrichment | 8 |
| `kegg_enrichment` | KEGG 富集分析 | enrichment | 8 |
| `gsea_prerank` | GSEA 预排序富集 | enrichment | 10 |
| `ml_binary_classification` | ML 二分类 | ml | 12 |
| `multi_model_comparison` | 多模型比较 | ml | 15 |
| `lasso_feature_selection` | LASSO 特征选择 | ml | 8 |
| `single_gene_expression` | 单基因表达分析 | single_gene | 8 |
| `gene_set_correlation` | 基因集相关性 | single_gene | 8 |
| `ppi_network_analysis` | PPI 网络分析 | network_pharmacology | 8 |
| `network_pharm_full` | 网络药理学全流程 | network_pharmacology | 12 |

**格式**: 支持纯 YAML 和 SKILL.md（YAML frontmatter + Markdown body）
**导出**: `skill_export.py` 可将任意 Skill 导出为独立 SKILL.md 文件

---

## 9. 工具执行 Harness

工具执行基础设施为所有 45+ 工具提供统一的生命周期管理。

### 9.1 资源限制 (Resource Limits)

`ResourceMonitor` (`tool_runner.py`) 使用 `psutil` 监控每次工具调用：

| 限制类型 | 默认值 | 说明 |
|---------|--------|------|
| 超时 | 600s (默认) / 3600s (R工具) | `ThreadPoolExecutor` + `future.result(timeout=...)` |
| 内存 | 4096MB (默认) / 8192MB (R工具) | `psutil.Process().memory_info().rss` 峰值追踪 |
| CPU | 仅记录不限制 | 平均 CPU 占比记录到 `ResourceUsage` |

`register_tool()` 支持 `timeout` / `max_memory_mb` 参数按工具覆盖。

### 9.2 审计日志 (Audit Logs)

`audit.py` 将每次工具执行的完整溯源持久化到 `tool_executions` 表：

- 非阻塞写入：独立 `SessionLocal`，异常不向上传播
- 记录字段：tool_name, category, parameters, status, started_at, finished_at, runtime_seconds, errors, warnings, output_files, resource_usage
- 查询接口：`get_tool_executions_by_session()` / `get_tool_execution_by_job_id()`

### 9.3 恢复策略 (Recovery Strategies)

6 种自动恢复策略（`recovery_strategies.py`）：

| 策略 | 触发条件 | 恢复动作 |
|------|---------|---------|
| `REnvironmentRecovery` | Rscript/package/library 错误 | `scan_system_config()` |
| `FileParseRecovery` | 文件不存在/parse/encoding 错误 | `probe_unknown_file()` |
| `TimeoutRecovery` | 工具超时 | 不自动重试，给出降级建议 |
| `ColumnMissingRecovery` | missing column / 列不存在 | `preview_table_file()` 列真实列名 |
| `DependencyRecovery` | package/library 缺失 | `scan_system_config()` 诊断 |
| `EncodingRecovery` | UnicodeDecode / 编码错误 | `probe_unknown_file()` 探测编码 |

工具可通过 `register_tool(recovery_strategies=[...])` 注册自定义策略。

### 9.4 并行执行 (Parallel Execution)

`parallel_executor.py` 支持依赖感知的并行执行：

- Planner 输出 `parallel_groups` 标注可并行步骤
- 拓扑排序后分批，每批内 `ThreadPoolExecutor` 并发
- 支持 `$step_N` 参数引用传递结果

### 9.5 Waterfall Racing (竞速执行)

`racing_executor.py` 参考 Firecrawl 的多引擎竞速：

- `register_tool(racing_group="deg_analysis")` 声明竞速组
- 同组工具同时启动，`concurrent.futures.as_completed` 取第一个成功
- 示例：`run_bulk_rnaseq_deg_analysis` 和 `run_deseq2_count_deg_analysis` 同属 `deg_analysis`

### 9.6 子Agent 委派 (Sub-Agent Delegation)

`sub_agent_manager.py` + `orchestrator.py` 参考 Hermes agent：

- `SubAgentManager`：轻量 Executor 变体，聚焦单一目标
- `Orchestrator`：Kanban 板（TODO→IN_PROGRESS→DONE），依赖感知调度
- `Delegator Agent`：LLM 判断复杂任务是否应拆分（特性开关控制）

### 9.7 循环护栏 (Loop Guardrails)

- **空转检测**：`(tool_name, hash(args))` 指纹，≥3 次相同调用 → 终止
- **熔断器**：连续 3 个工具错误 → 停止执行
- **致命错误**：参数签名错误、不存在的工具 → 立即停止

### 9.8 Lifecycle 完整流程

```
run_tool_with_lifecycle(tool_name, func, args, session_id):
    ├─ create_tool_context()       → job_id / job_dir
    ├─ 注入 session_id, job_dir, context
    ├─ [Hook] PRE_TOOL_EXECUTION
    ├─ 解析资源限制 (timeout / memory)
    ├─ ResourceMonitor.start()
    ├─ ThreadPoolExecutor + future.result(timeout)
    ├─ TimeoutError → error ToolResult
    ├─ ResourceMonitor.stop() → ResourceUsage
    ├─ [Hook] POST_TOOL_EXECUTION
    ├─ normalize_tool_result()
    ├─ collect_generated_files() + merge_output_files()
    ├─ 填充 provenance (含 resource_usage)
    └─ audit_tool_execution() → tool_executions 表 (non-blocking)
```

---

## 10. R 集成方案

### 9.1 架构

```
Python (FastAPI)
    │
    │ subprocess.run([rscript, script_path])
    ▼
Rscript.exe (R 4.2+)
    │
    │ .libPaths(R_LIBS_USER)
    ▼
env/r_libs/  (私有 R 包库)
    ├── survival/
    ├── limma/
    ├── DESeq2/
    ├── Seurat/
    └── ...
```

### 9.2 核心组件

**Rscript 定位** (`runtime_paths.py:find_rscript()`)：
1. 环境变量 `RSCRIPT_PATH`
2. 项目内置 `env/R/bin/Rscript.exe`
3. 系统 PATH 中的 `Rscript`
4. Windows 注册表（`HKLM\SOFTWARE\R-core\R`）
5. 常见安装路径（`C:\Program Files\R\`, `D:\R-*`）
6. Linux 路径（`/usr/bin/Rscript`, `/opt/R/bin/Rscript`）

**R 子进程环境** (`build_r_subprocess_env()`)：
- 注入 `R_LIBS_USER` → 项目私有 R 包库路径
- 注入 `UPLOAD_DIR` / `GENERATED_DIR` → 数据读写路径
- 强制 UTF-8 编码（`LANG=en_US.UTF-8`, `PYTHONIOENCODING=utf-8`）
- Windows 下设置 `R_DEFAULT_PACKAGES` 和 `HOME`

**R 代码模板** (`r_tools.py` 中的 r_prelude)：
- 自动注入 `smart_read()` 函数：多路径智能文件查找
- 设置 `GENERATED_DIR` 为唯一任务输出目录
- 每个任务独立的 `job_dir`

### 9.3 R 包管理

通过 `install_r_packages.R` 脚本管理，分 4 个阶段安装：

| 阶段 | 来源 | 包列表 |
|------|------|--------|
| Phase 1 | CRAN | data.table, ggplot2, pheatmap, survival, glmnet, timeROC, pROC, caret, randomForest, e1071, dplyr, patchwork |
| Phase 2 | Bioconductor | limma, org.Hs.eg.db, org.Mm.eg.db |
| Phase 3A | CRAN | survminer, msigdbr |
| Phase 3B | Bioconductor | GSVA, DESeq2, clusterProfiler, enrichplot |
| Phase 4 | CRAN | SeuratObject, Seurat |

所有包安装到 `env/r_libs/`，使用 `BiocManager` 处理 Bioconductor 依赖。

---

## 11. 数据库设计

### 11.1 ER 图

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  chat_sessions  │     │  chat_messages   │     │  stored_files   │     │ tool_executions │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (PK)         │────→│ id (PK)          │     │ id (PK)         │     │ id (PK)         │
│ session_id (UQ) │     │ session_id (FK)  │←────│ session_id (FK) │     │ session_id (FK) │
│ title           │     │ role             │     │ filename        │     │ job_id (UQ)     │
│ created_at      │     │ content          │     │ relative_path   │     │ tool_name       │
│ updated_at      │     │ created_at       │     │ file_type       │     │ status          │
└─────────────────┘     └──────────────────┘     │ source_type     │     │ parameters_json │
                                                  │ created_at      │     │ runtime_seconds │
                                                  └─────────────────┘     │ resource_json   │
                                                                         │ created_at      │
                                                                         └─────────────────┘
```

### 11.2 表结构

**chat_sessions** — 会话表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| session_id | VARCHAR UNIQUE | 前端生成的会话 ID |
| title | VARCHAR | 会话标题（自动从第一条消息/文件名生成） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

**chat_messages** — 消息表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| session_id | VARCHAR FK | 关联会话 |
| role | VARCHAR | user / assistant / system |
| content | TEXT | 消息内容 |
| created_at | DATETIME | 创建时间 |

**stored_files** — 文件表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| session_id | VARCHAR FK | 关联会话 |
| filename | VARCHAR | 文件名 |
| relative_path | VARCHAR | 相对路径（如 `uploads/abc/data.csv`） |
| file_type | VARCHAR | image / table / text / other |
| source_type | VARCHAR | upload / generated |
| created_at | DATETIME | 创建时间 |

**tool_executions** — 工具有执行审计日志表 (Feature 2)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| session_id | VARCHAR FK | 关联会话 |
| job_id | VARCHAR UQ | 工具有调用唯一 ID |
| tool_name | VARCHAR | 工具名 |
| tool_category | VARCHAR | 工具类别 |
| status | VARCHAR | success / error / partial |
| parameters_json | TEXT | 调用参数 JSON |
| started_at | VARCHAR | 开始时间 ISO 8601 |
| finished_at | VARCHAR | 结束时间 ISO 8601 |
| runtime_seconds | FLOAT | 执行耗时 |
| message | TEXT | 结果消息 |
| errors_json | TEXT | 错误列表 JSON |
| warnings_json | TEXT | 警告列表 JSON |
| output_files_json | TEXT | 输出文件列表 JSON |
| resource_usage_json | TEXT | 资源使用 JSON |
| retry_count | INTEGER | 重试次数 |
| recovery_attempts_json | TEXT | 恢复记录 JSON |
| created_at | DATETIME | 记录创建时间 |

### 11.3 数据库配置

- **引擎**：SQLite（单文件 `backend/db_data/app.db`）
- **连接参数**：`check_same_thread=False`（FastAPI 异步兼容）
- **Session 管理**：FastAPI 依赖注入，请求结束自动关闭

---

## 12. API 接口

### 12.1 聊天接口

**POST `/api/chat`**

```json
// Request
{
  "session_id": "abc123",
  "messages": [
    {"role": "user", "content": "帮我做这个表达矩阵的生存分析"},
    {"role": "assistant", "content": "好的，我先预览文件..."}
  ],
  "attached_files": [
    {
      "filename": "expression.csv",
      "relative_path": "uploads/abc123/expression.csv",
      "type": "table"
    }
  ]
}

// Response
{
  "reply": "## 分析完成\n\n...",
  "files": [
    {
      "name": "km_curve.png",
      "url": "/files/generated/abc123/r_job_xxx/km_curve.png",
      "type": "image",
      "relative_path": "generated/abc123/r_job_xxx/km_curve.png"
    }
  ],
  "session_id": "abc123",
  "title": "expression.csv"
}
```

### 12.2 文件上传

**POST `/api/upload`** (multipart/form-data)
- `files`: 文件列表
- `session_id`: 会话 ID

**GET `/api/uploads/{session_id}`** — 列出上传文件

**DELETE `/api/uploads/{session_id}/{filename}`** — 删除上传文件

### 12.3 会话历史

**GET `/api/history`** — 所有会话列表（含消息数、文件数）

**GET `/api/history/{session_id}`** — 某会话的完整消息和文件

### 12.4 会话删除

**DELETE `/api/chat/session/{session_id}`**
- 删除数据库记录（session + messages + files）
- 删除磁盘文件（uploads + generated）
- 清理后端 Session Memory

### 12.5 系统接口

**GET `/api/system-info`** — 后端环境信息（Python/R/Git/CPU/路径）

**GET `/api/health`** — 健康检查

---

## 13. 前端架构

前端是 Vite + React 构建的 SPA，打包为静态文件放在 `backend/static/`：

- `index.html` — 入口 HTML
- `assets/index-*.js` — 打包后的 JavaScript bundle
- `assets/index-*.css` — 打包后的 CSS

FastAPI 通过以下机制服务前端：
1. `/` → 返回 `index.html`
2. `/assets/*` → StaticFiles 挂载
3. `/{path}` → SPA 路由兜底（返回 `index.html`，React Router 处理路由）
4. `/api/*` / `/files/*` 不参与兜底 → 正常 API 响应

---

## 14. 会话与上下文管理

### 14.1 Session Memory

`context_manager.py` 实现了服务端会话记忆：

**核心机制**：
- 以 `session_id` 为 key 的进程内字典 `SESSION_MEMORY`
- 无合法 session_id → 不启用长期记忆（避免串会话）
- 每轮结束后调用 `remember_agent_turn()` 写入

**存储内容**：
- 会话压缩摘要（summary）
- 上一轮助手回复（last_assistant_answer）
- 可选项映射（pending_choices，支持 "选1" 短回复）
- 上一轮生成文件（last_output_files）
- 工具执行摘要（last_tool_observations）

**短回复解析** (`resolve_short_user_reply`)：
- 用户输入 "1" / "选 2" / "第三个" → 自动匹配上一轮的编号选项
- 将短回复展开为完整意图描述，注入到消息列表

### 14.2 上下文压缩

`maybe_compact_context()` 在每轮对话开始时运行：
- 保留最近 8 条消息
- 更早的消息通过 LLM 压缩为摘要
- 摘要不断追加合并（最长 3000 字符）

---

## 15. 规则、Hooks 与命令

### 15.1 结构化规则引擎

`rules_engine.py` 将硬编码 prompt 规则迁移为结构化 Rule 对象：

- **22 条内置规则**，按 category 分组（safety / quality / output / tool_usage / bioinformatics）
- 按 Agent 角色过滤（`applies_to: ["executor", "reporter"]`）
- 按工具类别激活（`tool_categories: ["survival", "file_io"]`）
- `RulesEngine.get_active_rules(categories, agent_role)` → `format_rules()` 输出 prompt 文本

**示例规则**：
```python
Rule(
    rule_id="no_fabricate_files",
    category="safety",
    directive="不要编造不存在的文件、列名、分析结果",
    priority="must",
)
```

### 15.2 Hook 系统

`hooks.py` 提供 4 个生命周期钩子点：

| Hook Point | 触发时机 | 默认回调 |
|-----------|---------|---------|
| `PRE_TOOL_EXECUTION` | 工具有执行前 | — |
| `POST_TOOL_EXECUTION` | 工具有执行后 | `error_notification`（错误日志写入） |
| `PRE_REPORTING` | Reporter 前 | — |
| `POST_AGENT_TURN` | Agent 轮次后 | `cleanup_temp_files`（清理 1h 以上临时文件） |

`hook_manager.register(HookPoint, callback)` 注册自定义回调，失败不影响主流程。

### 15.3 斜杠命令

`commands.py` 提供 19 个快捷命令，以 `/` 开头直接映射 Skill 或工具类别：

| 命令 | 映射 | 说明 |
|------|------|------|
| `/survival` | `single_gene_survival` | 单基因生存分析 |
| `/cox` | `univariate_cox_batch` | 批量 Cox 回归 |
| `/lasso` | `lasso_cox_model` | LASSO-Cox 模型 |
| `/deg` | `bulk_rnaseq_deg` | 差异表达（limma） |
| `/deseq2` | `deseq2_count_deg` | DESeq2 差异分析 |
| `/pca` | `bulk_pca_analysis` | PCA 分析 |
| `/enrich` | `go_enrichment` | GO/KEGG 富集 |
| `/gsea` | `gsea_prerank` | GSEA 富集 |
| `/ml` | `ml_binary_classification` | ML 分类 |
| `/compare` | `multi_model_comparison` | 多模型比较 |
| `/ppi` | `ppi_network_analysis` | PPI 网络 |
| `/netpharm` | `network_pharm_full` | 网络药理学 |
| `/scrna` | `scrna_standard_pipeline` | 单细胞分析 |
| `/probe` | `file_probe` | 文件探测 |
| `/geo` | `geo_data_download` | GEO 下载 |
| `/lit` | `literature` | 文献检索 |
| `/env` | `system` | 环境检测 |
| `/help` | — | 显示所有命令 |

命令解析在 Router 之前执行（`router_agent.py:_try_resolve_command()`），跳过 LLM 调用。

---

## 16. 特性开关

`agent_constants.py` 中的 `FEATURE_FLAGS` 控制所有新功能的启用/禁用：

```python
FEATURE_FLAGS = {
    "parallel_execution": True,       # 依赖感知并行执行
    "waterfall_racing": True,         # Waterfall Racing 竞速
    "sub_agent_delegation": False,    # 子Agent委派（需更多测试）
    "structured_rules_engine": True,  # 结构化规则引擎
    "hooks_enabled": True,            # Hook 系统
    "slash_commands": True,           # 斜杠命令
    "idempotent_guard": True,         # 空转检测
    "circuit_breaker": True,          # 熔断器
    "skill_improver": True,           # 自改进反馈
    "skill_md_support": True,         # SKILL.md 格式
}
```

所有新功能默认可独立开关，不影响核心流程。

---

## 17. 部署与运维

### 17.1 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | 3.10 / 3.11 / 3.12 |
| R | 4.2+ |
| 操作系统 | Windows 10/11 (主), Linux (兼容) |

### 17.2 快速启动

```batch
# 1. 环境检测
check_env.bat

# 2. 安装 R 包（首次）
Rscript install_r_packages.R

# 3. 启动应用
start_app.bat
```

`start_app.bat` 自动完成：
1. 检测项目文件完整性
2. 定位 Python 解释器
3. 创建/激活虚拟环境
4. 安装 Python 依赖
5. 定位 Rscript
6. 创建必要的运行时目录
7. 启动 Uvicorn 后端服务
8. 打开浏览器访问 `http://127.0.0.1:8000`

### 17.3 便携版构建

```batch
build_portable.bat
```

将项目打包到 `release/portable/`，包含：
- 后端代码
- 前端静态文件
- R 私有包库
- 启动脚本
- requirements.txt

### 17.4 配置后端环境变量

编辑 `backend/.env`：

```env
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat
API_HOST=127.0.0.1
API_PORT=8000
```

---

## 18. 开发指南

### 18.1 新增工具

```python
# backend/app/tools/my_new_tools.py

from app.agent.tool_registry import register_tool
from app.agent.tool_result import make_success_result, make_error_result

@register_tool(
    name="my_new_analysis",
    description="我的新分析工具",
    category="survival",           # 工具类别
    tags=["cox", "survival"],      # 搜索标签
    timeout=1800,                   # 超时 30 分钟 (Feature 1)
    max_memory_mb=8192,             # 内存告警 8GB (Feature 1)
    racing_group="survival_km",     # 竞速组 (Phase 1.2)
    recovery_strategies=[...],      # 自定义恢复策略 (Feature 3)
)
def my_new_analysis(file_path: str, gene: str, threshold: float = 0.05):
    """执行分析并返回标准 ToolResult"""
    try:
        # ... 执行分析逻辑 ...
        return make_success_result(
            message="分析完成",
            output_files=[
                {"name": "result.csv", "url": "/files/generated/xxx/result.csv",
                 "relative_path": "generated/xxx/result.csv"}
            ],
            summary={"up": 150, "down": 80}
        )
    except Exception as e:
        return make_error_result(
            message=f"分析失败: {str(e)}",
            errors=[str(e)]
        )

# 在 backend/app/tools/__init__.py 中添加导入：
# from . import my_new_tools  # noqa
```

### 18.2 新增 Skill

推荐使用 YAML 格式（`backend/app/agent/skills/packs/my_skill.yaml`）：

```yaml
skills:
  - skill_id: my_custom_skill
    name: "自定义分析"
    category: transcriptome
    description: "自定义转录组分析流程"
    task_types: [bioinformatics]
    subtask_types: [custom_analysis]
    trigger_keywords_cn: [自定义, 特殊分析]
    allowed_tools: [run_bulk_rnaseq_deg_analysis, preview_table_file]
    tool_categories: [transcriptome, file_io]
    max_tool_rounds: 12
    parameter_rules:
      - param_name: control_group
        strategy: from_file_preview
        rule_description: "从分组文件中自动检测"
    clarification_rules:
      - condition: ambiguous_control
        question_template: "哪个是对照组?"
        priority: required
    report_sections:
      - section_id: overview
        title: "结果概述"
        content_hint: "完成的分析项目和关键发现"
        order: 1
    implementation_status: implemented
    priority: medium
    examples:
      - user_input: "做自定义转录组分析"
```

也支持 SKILL.md 格式（YAML frontmatter + Markdown body），或 Python 方式注册（见 `skill_models.py:SkillSpec`）。

### 18.3 工具调用最佳实践

1. **返回 ToolResult**：新工具应返回标准 `ToolResult` 或使用 `make_success_result()`/`make_error_result()`
2. **声明 output_files**：显式列出所有输出文件，确保前端能展示
3. **参数验证**：在工具开头检查必填参数，提前返回 error
4. **异常处理**：用 try/except 捕获所有异常，返回友好的错误信息
5. **文件路径**：使用 `resolve_file_path()` 解析用户输入的文件路径
6. **R 代码**：通过 `run_r_analysis()` 执行，不要在工具中直接调用 subprocess

### 18.4 代码规范

- **工具名**：`snake_case`，使用动词开头（`run_`, `calculate_`, `preview_`, `search_`）
- **Category**：必须从 16 个预定义类别中选择
- **参数名**：统一使用 `file_path`（非 `path`）、`nrows`（非 `n`）、`session_id`
- **Agent 日志**：使用 emoji 前缀打印关键节点（🧭 Router, 📝 Planner, ⚙️ Executor, 🔁 Round）
- **错误日志**：使用 `🔥` 前缀标记异常

### 18.5 项目常量

定义在 `agent_constants.py`：

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_TOOL_CONTENT_CHARS` | 12000 | 工具返回内容截断阈值 |
| `MAX_FINAL_ANSWER_CHARS` | 30000 | 最终回复截断阈值 |
| `IMAGE_EXTS` | ('.png','.jpg','.jpeg','.svg','.gif','.webp') | 图片扩展名 |
| `PDF_EXTS` | ('.pdf',) | PDF 扩展名 |
| `DEFAULT_TOOL_TIMEOUT_SECONDS` | 600 | 默认单工具超时 |
| `MAX_TOOL_TIMEOUT_SECONDS` | 3600 | 超时硬上限 |
| `DEFAULT_MAX_MEMORY_MB` | 4096 | 默认内存告警阈值 |
| `MAX_CONSECUTIVE_ERRORS` | 3 | 熔断器阈值 |
| `MAX_IDEMPOTENT_CALLS` | 3 | 空转检测阈值 |
| `FEATURE_FLAGS` | dict | 10 个特性开关 |

### 18.6 测试

```bash
# 工具返回协议测试 (18 tests)
.venv/Scripts/python.exe backend/tests/test_tool_result.py

# 工具生命周期测试 (13 tests)
.venv/Scripts/python.exe backend/tests/test_tool_lifecycle.py

# 工具注册测试 (7 tests)
.venv/Scripts/python.exe backend/tests/test_tool_registration.py

# Skill 系统测试
.venv/Scripts/python.exe backend/tests/test_skill_system.py
.venv/Scripts/python.exe backend/tests/test_skill_packs.py

# 全量回归测试
.venv/Scripts/python.exe backend/tests/test_integration.py
```

---

## 附录 A：工具类别与关键词映射

| 类别 | 中文关键词 | 英文关键词 |
|------|-----------|-----------|
| survival | 生存, 预后, cox, km, 风险模型 | survival, cox, kaplan, lasso-cox, risk model |
| transcriptome | 差异分析, 差异表达, 转录组 | deg, deseq2, limma, bulk, rnaseq, pca |
| enrichment | 富集, 通路 | go, kegg, gsea, gsva, pathway |
| ml | 机器学习, 分类 | random forest, svm, xgboost, auc |
| file_io | 文件, 预览, 读取 | file, preview, csv, tsv, xlsx |
| system | r环境, rscript, 系统 | system, config, environment |
| network_pharmacology | 网络药理, ppi, 靶点 | network, ppi, string, compound |
| perturbation | 敲低, 敲除, 扰动 | knockdown, knockout, perturbation |
| scrna | 单细胞 | scrna, single cell, seurat, marker |
| spatial | 空间转录组 | spatial |
| modeling | 蛋白, 结构, 分子对接 | docking, protein, pdb, structure |
| drug_screening | 药物筛选 | drug, screening |
| aptamer | 适配体 | aptamer |
| literature | 文献, 论文 | literature, paper, pubmed |
| basic | gc含量 | gc_content |
| general | 通用 | — |

## 附录 B：文件类型检测

`file_utils.py:detect_file_type()` 根据扩展名推断：

| 扩展名 | 类型 |
|--------|------|
| .png, .jpg, .jpeg, .svg, .gif, .webp | image |
| .csv, .tsv, .xlsx, .xls | table |
| .txt, .md, .log | text |
| .pdf | pdf |
| .rds, .rdata, .rda | r_data |
| .zip, .gz, .tar | archive |
| 其他 | other |
