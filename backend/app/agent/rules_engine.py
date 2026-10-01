"""
结构化规则引擎 (Phase 5.1: Rules Engine).

参考 ECC 的 Rules 系统，将 task_prompts.py 中硬编码的规则
迁移为结构化 Rule 对象，支持按 Agent 角色和工具类别动态激活。

用法:
    from app.agent.rules_engine import RulesEngine
    engine = RulesEngine()
    rules = engine.get_active_rules(categories=["survival"], agent_role="executor")
    prompt = engine.format_rules(rules)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Rule(BaseModel):
    """单条规则定义。"""
    rule_id: str = ""
    category: str = "general"  # safety / quality / output / tool_usage / bioinformatics
    condition: str = ""        # 触发条件描述
    directive: str = ""        # 规则文本（注入 prompt）
    priority: str = "must"     # must / should / may
    applies_to: List[str] = Field(default_factory=lambda: ["executor", "reporter"])
    tool_categories: List[str] = Field(default_factory=list)  # 空=全部


# ============================================================
# 核心规则库（从 task_prompts.py 迁移）
# ============================================================

CORE_RULES: List[Rule] = []


def _init_core_rules():
    """初始化内置规则库（惰性加载）。"""
    global CORE_RULES
    if CORE_RULES:
        return

    CORE_RULES = [
        # --- 通用执行规则 ---
        Rule(
            rule_id="no_fabricate_files",
            category="safety",
            condition="always",
            directive="不要编造不存在的文件、列名、分组名、基因名、分析结果、图表、论文、DOI、PMID、PMCID 或工具输出",
            priority="must",
        ),
        Rule(
            rule_id="no_pretend_completion",
            category="safety",
            condition="always",
            directive="不要假装已经完成未执行的分析",
            priority="must",
        ),
        Rule(
            rule_id="real_output_only",
            category="output",
            condition="always",
            directive="所有生成结果必须来自工具返回。不要编造不存在的图片、PDF 或下载链接",
            priority="must",
        ),
        Rule(
            rule_id="error_transparency",
            category="quality",
            condition="on_tool_error",
            directive="如果工具报错，应如实说明错误原因，并给出修复建议",
            priority="must",
        ),
        Rule(
            rule_id="missing_input_clarify",
            category="quality",
            condition="missing_input",
            directive="如果用户输入不完整，应明确指出缺少什么，不要猜测",
            priority="must",
        ),
        Rule(
            rule_id="prefer_tool_over_theory",
            category="tool_usage",
            condition="analysis_task",
            directive="对需要计算、作图、建模的任务，优先调用工具执行，而不是只给理论步骤",
            priority="should",
        ),

        # --- 文件与输出规则 ---
        Rule(
            rule_id="preview_before_analyze",
            category="tool_usage",
            condition="file_task",
            directive="文件分析任务优先预览文件，再决定分析方案",
            priority="must",
            tool_categories=["file_io"],
        ),
        Rule(
            rule_id="real_image_markdown",
            category="output",
            condition="has_images",
            directive="如果有图片文件，最终回复必须使用 Markdown 图片格式展示真实 URL：![图片说明](真实url)",
            priority="must",
            applies_to=["reporter"],
        ),
        Rule(
            rule_id="no_placeholder_output",
            category="output",
            condition="always",
            directive="不要输出 :contentReference、oaicite、index 等占位符",
            priority="must",
            applies_to=["executor", "reporter"],
        ),
        Rule(
            rule_id="prevent_huge_output",
            category="output",
            condition="large_data",
            directive="不要输出海量原始数据，应保存为文件或总结关键结果",
            priority="must",
        ),

        # --- R 分析规则 ---
        Rule(
            rule_id="no_install_in_r",
            category="safety",
            condition="r_analysis",
            directive="禁止在 R 代码中执行 install.packages()、BiocManager::install()、pip install 或其他联网安装",
            priority="must",
            tool_categories=["single_gene", "survival", "transcriptome", "enrichment", "ml", "perturbation", "scrna", "spatial"],
        ),
        Rule(
            rule_id="r_plot_explicit_close",
            category="quality",
            condition="r_plot",
            directive="R 画图必须显式 dev.off()，或使用 ggsave",
            priority="must",
            tool_categories=["single_gene", "survival", "transcriptome", "enrichment", "ml"],
        ),
        Rule(
            rule_id="r_package_missing_report",
            category="quality",
            condition="r_missing_package",
            directive="缺少 R 包时必须如实报错，不要假装成功",
            priority="must",
            tool_categories=["single_gene", "survival", "transcriptome", "enrichment", "ml", "perturbation", "scrna", "spatial"],
        ),

        # --- 表达数据预处理 ---
        Rule(
            rule_id="expression_auto_preprocess",
            category="bioinformatics",
            condition="expression_data",
            directive="用户未说明表达尺度时，expression_preprocess 默认使用 auto。不要重复 log2 已 log2 的数据",
            priority="must",
            tool_categories=["single_gene", "survival", "transcriptome", "enrichment", "ml"],
        ),
        Rule(
            rule_id="raw_count_warning",
            category="bioinformatics",
            condition="raw_count_cox_ml",
            directive="raw count 不应直接用于 Cox/预后建模或普通 ML/相关性分析，应提醒用户",
            priority="must",
            tool_categories=["survival", "ml", "single_gene"],
        ),

        # --- 文献规则 ---
        Rule(
            rule_id="literature_must_search",
            category="quality",
            condition="literature_task",
            directive="文献检索必须调用 search_literature 工具，不要编造 DOI、PMID、期刊或结论",
            priority="must",
            tool_categories=["literature"],
        ),

        # --- 生存分析规则 ---
        Rule(
            rule_id="survival_confirm_time_status",
            category="bioinformatics",
            condition="survival_task",
            directive="必须确认 time_col 和 status_col 存在。status_col 通常应为 0/1",
            priority="must",
            tool_categories=["survival"],
        ),

        # --- 安全声明 ---
        Rule(
            rule_id="research_not_clinical",
            category="safety",
            condition="prognostic_model",
            directive="预后模型/风险评分仅用于研究，不是临床决策工具",
            priority="must",
            tool_categories=["survival", "ml"],
        ),
        Rule(
            rule_id="virtual_not_experimental",
            category="safety",
            condition="virtual_analysis",
            directive="虚拟敲除/分子对接是计算模拟，不等同于真实实验结果，需要实验验证",
            priority="must",
            tool_categories=["perturbation", "modeling"],
        ),
        Rule(
            rule_id="network_pharm_disclaimer",
            category="safety",
            condition="network_pharm",
            directive="网络药理学结果是数据库整合和网络推断，不等于真实药效证明",
            priority="must",
            tool_categories=["network_pharmacology"],
        ),
    ]


class RulesEngine:
    """
    规则引擎：按 Agent 角色和工具有类别过滤并格式化规则。
    """

    def __init__(self):
        _init_core_rules()

    def get_active_rules(
        self,
        categories: List[str] = None,
        agent_role: str = "executor",
    ) -> List[Rule]:
        """
        获取当前上下文下应激活的规则。

        Args:
            categories: 当前工具类别列表（如 ["survival", "file_io"]）
            agent_role: 当前 Agent 角色（router/planner/executor/reporter）

        Returns:
            激活的 Rule 列表
        """
        cats = set(categories or [])
        active = []

        for rule in CORE_RULES:
            # 角色过滤
            if agent_role not in rule.applies_to:
                continue

            # 类别过滤：rule.tool_categories 为空 → 全局规则
            if rule.tool_categories and cats:
                if not any(c in cats for c in rule.tool_categories):
                    continue

            active.append(rule)

        return active

    def format_rules(self, rules: List[Rule]) -> str:
        """将规则列表格式化为 prompt 可用的文本块。"""
        if not rules:
            return ""

        # 按 category 分组
        groups: Dict[str, List[Rule]] = {}
        for r in rules:
            groups.setdefault(r.category, []).append(r)

        category_labels = {
            "safety": "安全规则",
            "quality": "质量规则",
            "output": "输出规则",
            "tool_usage": "工具使用规则",
            "bioinformatics": "生信分析规则",
            "general": "通用规则",
        }

        parts = []
        for cat, cat_rules in sorted(groups.items()):
            label = category_labels.get(cat, cat)
            parts.append(f"【{label}】")
            for r in cat_rules:
                prefix = {"must": "必须", "should": "应该", "may": "可以"}.get(r.priority, "")
                parts.append(f"- [{prefix}] {r.directive}")

        return "\n".join(parts)

    def format_for_agent(
        self,
        categories: List[str],
        agent_role: str,
    ) -> str:
        """一站式：获取规则并格式化。"""
        rules = self.get_active_rules(categories=categories, agent_role=agent_role)
        return self.format_rules(rules)
