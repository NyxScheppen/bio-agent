# 枚举 + 实体类型

> 范围：`backend/bioagent/enums.py`（3 个 `StrEnum`）、`backend/bioagent/types.py`（2 个 TypedDict + 4 个 dataclass）。
> 纯声明 spec：只定义类型，不含函数、不含序列化 helper、不含 DDL（DDL 在 03-db）。
> **本文件自包含（类型定义层面）**：枚举与实体的完整定义都内联在下文；实现只需再知道包根路径、Python 版本与工具链配置（见元信息），不依赖其它 spec 的定义。

## 元信息

- **前置依赖**：无（全部类型内联在本文件）
- **包根路径**：Python 包 `bioagent` 的源码在 `backend/bioagent/`（包根），import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）。`backend/bioagent/__init__.py` 为空文件、随包新建；前端是独立的 `frontend/` 目录，不在本包内。注：CLAUDE.md 里 `backend/tools/`、`runners/` 是早期目录写法，对应 `backend/bioagent/tools/`、`backend/bioagent/r_runner.py`（CLAUDE.md 已同步为 `backend/bioagent/`）。
- **运行环境 / 工具链**：Python 3.11+（`enum.StrEnum` 是 3.11 新增，本 spec 依赖）。质量门（`ruff check` / `pyright` strict / `pytest`）的工具链配置属「脚手架」交付物（`pyproject.toml` + `pyrightconfig.json`，实现脚手架阶段落地），非本 spec 内联；本 spec 只声明目标：`pyright` strict 零报错、`ruff` 零报错、`pytest` 全绿。

## 用户故事

> 作为 bio agent 系统的开发者，我想要一份全系统共享、pyright strict 下零告警的类型与枚举定义，以便后续每个 spec 引用同一套实体、各处不再重复定义。

## 验收标准

- [ ] `enums.py` 含 3 个 `StrEnum`，成员与「枚举」段代码逐字一致
- [ ] `types.py` 含 2 个 TypedDict + 4 个 dataclass，字段与「TypedDict」「dataclass」段代码逐字一致
- [ ] 所有枚举 `.value` 为小写 snake_case 字符串，可直接 `json.dumps` / 存 SQLite
- [ ] 固定键字段用 TypedDict、异构载荷用 `dict[str, Any]`（边界见「嵌套 dict 字段的边界」表）、不加 `frozen`
- [ ] `pyright` strict 下零报错：无 implicit Any、无 `str` 赋给枚举成员的默认值告警

## 技术方案

- **新文件**：`backend/bioagent/enums.py`、`backend/bioagent/types.py`（无 Facade、无 API、无数据变更）
- **约定**：枚举统一 `class X(StrEnum)`，成员 `UPPER_SNAKE`、值 = `成员名.lower()` 的 snake_case；dataclass 默认值用枚举成员而非裸字符串。
- **公开面**：`backend/bioagent/__init__.py` 保持空（不 re-export，随包新建）；引用一律 `from bioagent.enums import X` / `from bioagent.types import Y`，不从 `bioagent` 根导入；两模块不加 `__all__`（CLAUDE.md 禁 `*` 导入，`__all__` 是死代码）。
- **Category 可扩展性**：`Category` 是数据驱动的单一事实来源——所有枚举 category 的地方（router 意图列表、管线裁剪、工具发现）一律 `[c.value for c in Category]` 推导，**不写死任何类别名列表**。将来加类别（如 `ML` / `SINGLE_CELL`）= 加一个成员 + 写一个工具 spec，其余代码自动跟随，无数据迁移（值是纯字符串）。

### 枚举（`backend/bioagent/enums.py`，3 个）

```python
from enum import StrEnum


class Category(StrEnum):
    """工具类别。router 意图 → 类别子集裁剪的依据。

    加类别 = 加一个成员 + 丢一个工具文件到 backend/bioagent/tools/<category>/，无数据迁移。
    """
    DATA = "data"                    # 数据加载/预处理（表达矩阵、临床表）
    KNOWLEDGE = "knowledge"          # 知识库检索（RAG）
    SYSTEM = "system"                # 系统工具（文件上传、任务历史等）
    SINGLE_GENE = "single_gene"      # 单基因分析
    DGE = "dge"                      # 差异表达分析
    ENRICHMENT = "enrichment"        # 富集分析（GO/KEGG）
    NETWORK = "network"              # 网络药理（PPI、蛋白-靶点）
    SURVIVAL = "survival"            # 生存分析（KM/Cox）


class Runtime(StrEnum):
    """工具运行环境。"""
    PYTHON = "python"
    R = "r"


class TaskStatus(StrEnum):
    """任务状态（task 历史表 + 编排状态机）。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

### TypedDict（`backend/bioagent/types.py` 开头，2 个）

```python
from typing import TypedDict


class TokenUsageDict(TypedDict):           # 单次 LLM 记账 {input, output}
    input: int
    output: int


class EvalScores(TypedDict):               # eval 得分：报告质量 3 维 + 工具调用 2 维（「两者都判」）
    format: float                          # 报告格式规范性
    relevance: float                       # 报告与问题相关度
    completeness: float                    # 报告完整性
    intent_correct: float                  # router 意图判定是否正确
    tool_correct: float                    # planner 工具选择是否正确（plan 步骤的 tool 是否合适）
```

### dataclass（`backend/bioagent/types.py`，4 个）

> `from bioagent.enums import Category, Runtime`

```python
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# ---- 工具 ----
@dataclass
class ToolDefinition:
    """一个可自动发现的分析工具（backend/bioagent/tools/<category>/<name>.py 的 TOOL 导出）。

    Python 工具：run 是 async 执行体（r_script=None）；
    R 工具：r_script 是脚本文件名，相对 `config.storage.r_scripts_dir`（02-config 定义目录、06-r-runner 解析成绝对路径），run=None，由 executor 持 runner 执行（06-r-runner）。
    """
    name: str
    description: str
    category: Category
    runtime: Runtime
    input_schema: dict[str, Any]           # 给 LLM 的 JSON schema（参数定义，planner 拼进 prompt 用）
    output_schema: dict[str, Any]          # 结果的 JSON schema（前端渲染依据）
    run: Callable[..., Awaitable[dict[str, Any]]] | None   # Python 工具执行体；R 工具为 None
    r_script: str | None = None             # R 工具脚本名；Python 工具为 None
    frontend: dict[str, Any] = field(default_factory=dict[str, Any])  # 前端渲染提示（result_type 等）

# ---- LLM / eval ----
@dataclass
class LLMOutput:
    id: str                 # uuid4，由产出方（04-llm）生成
    module: str             # 产出模块（router/planner/executor/reporter/rag）
    type: str               # 产出类型（intent/plan/step/report/embedding）
    model: str              # 本次调用所用模型（供 TokenUsage.model）
    content: str            # 原始文本
    token_usage: TokenUsageDict
    correlation_id: str

@dataclass
class EvalReport:
    id: str
    output_id: str
    module: str
    type: str               # "report" | "tool_call"（判报告质量 / 判工具调用）
    scores: EvalScores      # 5 维；按 type 只填对应子集，其余 0
    token_usage: TokenUsageDict
    correlation_id: str
    created_at: float

@dataclass
class TokenUsage:           # 一次 LLM 调用记账（对应 token_usage 表）
    id: str
    correlation_id: str | None
    module: str
    purpose: str            # intent / plan / step / report / embedding / eval / ...
    model: str
    input_tokens: int
    output_tokens: int
    created_at: float
```

**`id` / `created_at` 约定**（跨 dataclass 统一）：所有 `id` 都是 uuid4 字符串（`str(uuid.uuid4())`），由创建该对象的模块生成（如 `LLMOutput` → 04-llm、`EvalReport` → 08-eval）；`created_at` 是 Unix epoch 秒（float，`time.time()`）。类型层只声明字段、不生成 id。

### 嵌套 dict 字段的边界（哪些收 TypedDict / 哪些留 `dict[str, Any]`）

| 字段 | 归属 | 理由 |
|---|---|---|
| `EvalReport.scores` | `EvalScores` | 固定 5 键（format/relevance/completeness/intent_correct/tool_correct） |
| `LLMOutput.token_usage` / `EvalReport.token_usage` | `TokenUsageDict` | 固定 2 键（input/output） |
| `ToolDefinition.input_schema` / `output_schema` | `dict[str, Any]` | 任意 JSON schema |
| `ToolDefinition.frontend` | `dict[str, Any]` | 前端渲染提示，键随 result_type 变 |

- **明确不做**：不加 `frozen`；`AgentState`（LangGraph 内部 state）留在 09-orchestration；`ChatRequest`/`TaskSummary`（API/DB 传输对象）留在各自 spec；工具结果的解析纯函数（如单基因表达统计 mean/median/sd + t 检验、`Embedder.embed`）留在各自工具 spec。
- **default_factory 约定**：`field(default_factory=dict)` 在 pyright strict 下报 `dict[Unknown]`，故用 `field(default_factory=dict[str, Any])`——参数化类型对象可调用、返回空容器，类型精确、pyright 零报错。

## 测试要点

- [ ] 单元测试 `tests/test_types/`（两个文件：`test_enums.py` 测枚举、`test_types.py` 测 TypedDict/dataclass）：
  - [ ] 3 个枚举**穷尽断言**（防漏成员/多成员/改值）：下方 `EXPECTED` 硬编码每个枚举的完整值集合，`{m.value for m in X} == expected` 逐枚举比对
  - [ ] 命名约定断言 `all(m.value == m.name.lower() for m in X)`（值 = 成员名小写，防手滑改值）
  - [ ] `json.dumps(Category.SINGLE_GENE) == '"single_gene"'`（StrEnum 可直接序列化）
  - [ ] `ToolDefinition("", "", Category.DGE, Runtime.PYTHON, {}, {}, async_fn).category is Category.DGE`
  - [ ] R 工具形状：`ToolDefinition("", "", Category.SURVIVAL, Runtime.R, {}, {}, None, "km.R").r_script == "km.R"` 且 `run is None`
  - [ ] `ToolDefinition(...).frontend` 两次实例化互不共享（`default_factory` 隔离）
  - [ ] 2 个 TypedDict 用 `get_type_hints` 断言键集合完整：`set(get_type_hints(EvalScores)) == {"format","relevance","completeness","intent_correct","tool_correct"}` 等

  > `async_fn` 是 `test_types.py` 里的占位可调用对象：`async def async_fn() -> dict[str, Any]: return {}`，作 `ToolDefinition.run` 的合法值（满足 `Callable[..., Awaitable[...]]`）。

  ```python
  EXPECTED = {
      Category: {"data", "knowledge", "system", "single_gene", "dge",
                 "enrichment", "network", "survival"},
      Runtime: {"python", "r"},
      TaskStatus: {"pending", "running", "completed", "failed"},
  }
  for enum_cls, expected in EXPECTED.items():
      assert {m.value for m in enum_cls} == expected
  ```
- [ ] 集成测试：无（纯声明，无管道）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新（格式：追加一条，含「新增了哪些测试 / 每个检查什么方向——功能正确·边界鲁棒·回归保护 / 属于哪个系统 / 在哪个功能阶段编写」，与文件里已有条目一致）
- [ ] 后续 spec（03-db 起）引用本 spec 的枚举/实体，形成单一事实来源
