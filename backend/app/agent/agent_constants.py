MAX_TOOL_CONTENT_CHARS = 12000
MAX_FINAL_ANSWER_CHARS = 30000

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp")
PDF_EXTS = (".pdf",)
DOWNLOADABLE_EXTS = (
    ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp",
    ".pdf", ".csv", ".tsv", ".txt", ".xlsx", ".xls",
    ".rds", ".rdata", ".json", ".zip"
)

# ============================================================
# 资源限制常量 (Feature 1: Resource Limits)
# ============================================================
DEFAULT_TOOL_TIMEOUT_SECONDS = 600       # 默认单工具超时（秒）
MAX_TOOL_TIMEOUT_SECONDS = 3600          # 硬上限
DEFAULT_MAX_MEMORY_MB = 4096             # 默认内存告警阈值（MB）
RESOURCE_CHECK_INTERVAL_SECONDS = 1.0    # psutil 采样间隔

# ============================================================
# 特性开关 (Phase 5.4: Feature Flags)
# ============================================================
FEATURE_FLAGS = {
    "parallel_execution": True,       # Phase 1: 依赖感知并行执行
    "waterfall_racing": True,         # Phase 1: Waterfall Racing 竞速
    "sub_agent_delegation": False,    # Phase 3: 子Agent委派（默认关闭，需更多测试）
    "structured_rules_engine": True,  # Phase 5: 结构化规则引擎
    "hooks_enabled": True,            # Phase 5: Hook 系统
    "slash_commands": True,           # Phase 5: 斜杠命令
    "idempotent_guard": True,         # Phase 4: 空转检测
    "circuit_breaker": True,          # Phase 4: 熔断器
    "skill_improver": True,           # Phase 4: 自改进反馈
    "skill_md_support": True,         # Phase 2: SKILL.md 格式
}