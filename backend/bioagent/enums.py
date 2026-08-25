from enum import StrEnum


class Category(StrEnum):
    """工具类别。router 意图 → 类别子集裁剪的依据。

    加类别 = 加一个成员 + 丢一个工具文件到 backend/bioagent/tools/<category>/，无数据迁移。
    """
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
    """任务状态（task 历史表的 status 列，消费方 = 10-api 的 task CRUD）。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
