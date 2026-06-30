"""
Skill data models.

A Skill is a higher-level task capability package that encapsulates:
- Trigger conditions (task_type, subtask_type, keywords)
- Required/optional inputs
- Default workflow template
- Allowed tools
- Parameter rules
- Clarification rules
- QC rules
- Report sections
- Examples
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class SkillExample(BaseModel):
    """技能触发示例，用于文档和测试。"""
    user_input: str = ""
    expected_skill_id: str = ""
    description: str = ""


class SkillClarificationRule(BaseModel):
    """
    在特定条件满足时触发追问的规则。

    condition 取值示例：
    - "missing_file"       — 缺少上传文件
    - "missing_time_col"   — 缺少生存时间列
    - "missing_group_col"  — 缺少分组列
    - "missing_gene"       — 缺少目标基因
    - "ambiguous_control"  — 无法确定 control 组
    - "too_few_samples"    — 样本数不足
    """
    condition: str = ""
    question_template: str = ""
    priority: str = "required"  # "required" | "suggested"


class SkillParameterRule(BaseModel):
    """
    参数自动补全规则。

    strategy 取值：
    - "from_file_preview" — 从文件预览中自动检测
    - "from_user"         — 需要用户明确提供
    - "auto_detect"       — 后端自动推断
    - "default"           — 使用默认值
    """
    param_name: str = ""
    strategy: str = "from_user"
    rule_description: str = ""
    default_value: Optional[Any] = None
    alternatives: List[str] = Field(default_factory=list)


class SkillReportSection(BaseModel):
    """报告章节定义。"""
    section_id: str = ""
    title: str = ""
    content_hint: str = ""
    order: int = 0


class SkillSpec(BaseModel):
    """
    技能规格定义。

    一个 Skill 封装了某类生信任务的完整元信息：
    - 何时触发
    - 需要什么输入
    - 使用什么 workflow
    - 暴露哪些工具
    - 参数如何补全
    - 何时追问用户
    - 最终报告如何组织
    """
    # --- 标识 ---
    skill_id: str = ""
    name: str = ""
    category: str = "general"
    description: str = ""

    # --- 触发匹配 ---
    task_types: List[str] = Field(default_factory=list)      # Router task_type 匹配
    subtask_types: List[str] = Field(default_factory=list)    # Router subtask_type 匹配
    trigger_keywords: List[str] = Field(default_factory=list) # 用户消息关键词
    trigger_keywords_cn: List[str] = Field(default_factory=list)

    # --- 输入要求 ---
    required_inputs: List[str] = Field(default_factory=list)
    optional_inputs: List[str] = Field(default_factory=list)

    # --- Workflow ---
    default_workflow_id: str = ""
    allowed_tools: List[str] = Field(default_factory=list)
    banned_tools: List[str] = Field(default_factory=list)
    tool_categories: List[str] = Field(default_factory=list)  # 技能涉及的工具类别
    max_tool_rounds: int = 8

    # --- 规则 ---
    parameter_rules: List[SkillParameterRule] = Field(default_factory=list)
    clarification_rules: List[SkillClarificationRule] = Field(default_factory=list)
    qc_rules: List[str] = Field(default_factory=list)
    safety_rules: List[str] = Field(default_factory=list)     # 安全限制规则

    # --- 报告 ---
    report_sections: List[SkillReportSection] = Field(default_factory=list)
    output_expectations: List[str] = Field(default_factory=list)

    # --- 文档 ---
    examples: List[SkillExample] = Field(default_factory=list)

    # --- 元信息 ---
    enabled: bool = True
    version: str = "1.0"
    implementation_status: str = "planned"  # implemented | partial | planned
    priority: str = "medium"                # high | medium | low
    ui_schema: Dict[str, Any] = Field(default_factory=dict)
