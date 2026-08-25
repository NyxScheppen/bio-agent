from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict

from bioagent.enums import Category, Runtime


class TokenUsageDict(TypedDict):           # 单次 LLM 记账 {input, output}
    input: int
    output: int


class EvalScores(TypedDict):               # eval 得分：报告质量 3 维 + 工具调用 2 维（「两者都判」）
    format: float                          # 报告格式规范性
    relevance: float                       # 报告与问题相关度
    completeness: float                    # 报告完整性
    intent_correct: float                  # router 意图判定是否正确
    tool_correct: float                    # planner 工具选择是否正确（plan 步骤的 tool 是否合适）


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
    module: str             # 产出模块（router/planner/reporter/eval）
    type: str               # 产出类型（intent/plan/report/eval）
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
    purpose: str            # intent / plan / report / eval（= LLMOutput.type）
    model: str
    input_tokens: int
    output_tokens: int
    created_at: float
