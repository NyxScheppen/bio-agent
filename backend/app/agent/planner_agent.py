from typing import Any, Dict, Optional

from app.agent.router_agent import call_json_agent
from app.agent.task_prompts import PLANNER_PROMPT
from app.agent.category_router import (
    normalize_categories,
    infer_categories_from_text,
    resolve_tool_categories,
)
from app.agent.tool_registry import get_tool_brief_by_categories

# 延迟导入避免循环
from app.agent.skills.skill_models import SkillSpec


def run_planner_agent(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    selected_skill: Optional[SkillSpec] = None,
) -> Dict[str, Any]:
    # --- Skill 驱动的类别推断 ---
    if selected_skill and selected_skill.allowed_tools:
        # 从 skill.allowed_tools 反推类别
        from app.agent.tool_registry import TOOL_META
        skill_cats = set()
        for tname in selected_skill.allowed_tools:
            meta = TOOL_META.get(tname, {})
            cat = meta.get("category", "")
            if cat:
                skill_cats.add(cat)
        router_categories = normalize_categories(list(skill_cats))
    else:
        router_categories = normalize_categories(router_result.get("tool_categories", []))

    if not router_categories:
        router_categories = infer_categories_from_text(
            context_pack.get("latest_user_message", "")
        )

    if not router_categories:
        router_categories = ["general"]

    workflow_policy = build_workflow_policy(router_categories)

    # --- Skill 驱动的工具列表 ---
    if selected_skill and selected_skill.allowed_tools:
        available_tools = _build_skill_tool_brief(selected_skill)
    else:
        available_tools = get_tool_brief_by_categories(
            categories=router_categories,
            include_file_io=True,
            fallback_all=True
        )

    # --- 构建 payload ---
    payload = {
        "context_summary": context_pack.get("summary", ""),
        "recent_messages": context_pack.get("recent_messages", []),
        "latest_user_message": context_pack.get("latest_user_message", ""),
        "router_result": router_result,
        "available_tools": available_tools,
        "workflow_policy": workflow_policy,
    }

    # --- Skill 信息注入 ---
    if selected_skill:
        payload["selected_skill"] = {
            "skill_id": selected_skill.skill_id,
            "name": selected_skill.name,
            "default_workflow_id": selected_skill.default_workflow_id,
            "required_inputs": selected_skill.required_inputs,
            "parameter_rules": [
                {"param_name": r.param_name, "strategy": r.strategy,
                 "description": r.rule_description, "default": r.default_value,
                 "alternatives": r.alternatives}
                for r in selected_skill.parameter_rules
            ],
            "clarification_rules": [
                {"condition": r.condition, "question": r.question_template,
                 "priority": r.priority}
                for r in selected_skill.clarification_rules
            ],
            "max_tool_rounds": selected_skill.max_tool_rounds,
        }
        payload["skill_prompt"] = _build_skill_planner_prompt(selected_skill)

    result = call_json_agent(PLANNER_PROMPT, payload)

    if not result:
        max_rounds = selected_skill.max_tool_rounds if selected_skill else 8
        result = {
            "objective": selected_skill.description if selected_skill else "根据用户需求执行分析",
            "execution_mode": "ask_user" if router_result.get("need_clarification") else "tool_execution",
            "tool_categories": router_categories or ["general"],
            "user_question_if_any": router_result.get("clarification_question", ""),
            "steps": [],
            "max_tool_rounds": max_rounds,
            "final_report_requirements": [
                "说明是否完成",
                "列出关键结果",
                "列出生成文件",
                "给出下一步建议"
            ]
        }

    # --- Skill 覆盖 ---
    if selected_skill:
        if not result.get("workflow_id"):
            result["workflow_id"] = selected_skill.default_workflow_id
        # skill 的 max_tool_rounds 作为上限
        if not result.get("max_tool_rounds") or result.get("max_tool_rounds", 0) <= 0:
            result["max_tool_rounds"] = selected_skill.max_tool_rounds
        # 注入 skill 参数规则
        result["skill_id"] = selected_skill.skill_id
        result["skill_parameter_rules"] = payload.get("selected_skill", {}).get("parameter_rules", [])
        result["skill_clarification_rules"] = payload.get("selected_skill", {}).get("clarification_rules", [])

    if router_result.get("need_clarification"):
        result["execution_mode"] = "ask_user"
        if not result.get("user_question_if_any"):
            result["user_question_if_any"] = router_result.get("clarification_question", "")

    if not result.get("tool_categories"):
        result["tool_categories"] = router_categories or ["general"]

    return result


def _build_skill_tool_brief(skill: SkillSpec) -> list:
    """从 Skill.allowed_tools 构建工具简介列表。"""
    from app.agent.tool_registry import get_tool_meta

    brief = []
    for tname in skill.allowed_tools:
        meta = get_tool_meta(tname)
        brief.append({
            "name": tname,
            "description": meta.get("description", ""),
            "category": meta.get("category", "general"),
            "tags": meta.get("tags", []),
        })
    return brief


def _build_skill_planner_prompt(skill: SkillSpec) -> str:
    """为 Planner 构建 Skill 特化提示。"""
    lines = [
        f"\n【当前激活 Skill: {skill.name} ({skill.skill_id})】",
        f"描述：{skill.description}",
    ]

    if skill.required_inputs:
        lines.append(f"必需输入：{', '.join(skill.required_inputs)}")

    if skill.clarification_rules:
        lines.append("追问规则：")
        for r in skill.clarification_rules:
            lines.append(f"  - 条件 {r.condition}: {r.question_template}")

    if skill.parameter_rules:
        lines.append("参数规则：")
        for r in skill.parameter_rules:
            lines.append(f"  - {r.param_name}: {r.strategy} — {r.rule_description}")

    if skill.default_workflow_id:
        lines.append(f"默认 Workflow: {skill.default_workflow_id}")

    if skill.qc_rules:
        lines.append(f"QC 步骤: {', '.join(skill.qc_rules)}")

    lines.append(f"最大工具轮次: {skill.max_tool_rounds}")
    lines.append("请严格遵守上述 Skill 定义规划步骤。")

    return "\n".join(lines)

def build_workflow_policy(categories: list) -> str:
    """
    根据工具组生成本轮 Planner 工作流策略。
    后续新增工具时，优先改这里或工具 metadata，不要到处硬编码。
    """
    cats = set(categories or [])

    rules = []

    rules.append(
        """
【通用文件规则】
1. 如果任务涉及上传文件，第一步优先预览/探测文件结构。
2. 如果标准预览失败、扩展名未知、压缩包、编码异常，应使用文件探测工具。
3. 不要猜列名；必须基于文件预览结果或用户明确提供的列名。
4. 如果缺少关键列名，应追问用户，而不是编造。
"""
    )

    if "system" in cats:
        rules.append(
            """
【系统环境任务规则】
1. 如果用户询问 R 环境、Rscript、依赖、R 包、PATH，优先调用 scan_system_config。
2. 需要明确告诉用户：检测的是后端服务器环境，不是浏览器客户端本机。
3. 如果 rscript_path 为空，说明后端进程 PATH 找不到 Rscript。
"""
        )

    if "survival" in cats:
        rules.append(
            """
【生存/预后分析工作流】
1. 单基因生存分析：
   - 必需参数：file_path, gene, time_col, status_col。
   - 首选工具：run_single_gene_survival_analysis。
2. 批量单因素 Cox：
   - 必需参数：file_path, feature_cols, time_col, status_col。
   - 首选工具：run_univariate_cox_batch。
3. LASSO-Cox：
   - 必需参数：file_path, feature_cols, time_col, status_col。
   - 首选工具：run_lasso_cox_model。
4. 多因素 Cox：
   - 必需参数：file_path, feature_cols, time_col, status_col。
   - 首选工具：run_multivariate_cox_analysis。
5. 风险评分模型：
   - 必需参数：file_path, feature_cols, time_col, status_col。
   - 首选工具：run_prognostic_risk_model。
6. 风险组 KM：
   - 必需参数：file_path, time_col, status_col，可选 risk_group_col。
   - 首选工具：run_risk_group_survival_analysis。
7. time-dependent ROC：
   - 必需参数：file_path, time_col, status_col, score_col, times。
   - 首选工具：run_time_roc_analysis。
8. 表达值预处理：
   - 除非用户明确要求，否则 expression_preprocess 使用 auto。
9. 如果用户只说“做预后模型”，但没有 feature_cols/time/status，应先预览文件，然后根据列名判断；无法判断则追问。
"""
        )

    if "transcriptome" in cats:
        rules.append(
            """
【bulk 转录组分析工作流】
1. bulk 标准化表达矩阵差异分析：
   - 需要 expression_file, group_file, control_group, treatment_group。
   - 首选工具：run_bulk_rnaseq_deg_analysis。
2. 原始 count 差异分析：
   - 如果用户说明是 raw count/count matrix，首选 run_deseq2_count_deg_analysis。
   - 需要 count_file, group_file, control_group, treatment_group。
3. PCA 分析：
   - 需要 expression_file，可选 group_file。
   - 首选工具：run_bulk_pca_analysis。
4. 表达矩阵一般要求第一列为 gene，后续列为样本。
5. 分组文件一般要求包含 sample 和 group 两列。
6. 如果用户没提供分组名，应先预览 group_file 中 group 列取值，再决定 control/treatment；不能猜。
"""
        )

    return "\n".join(rules)