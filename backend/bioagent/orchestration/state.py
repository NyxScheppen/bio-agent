from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 编排状态：各节点按职责增量读写的共享 dict。

    无 reducer，同名键后写覆盖；各节点只写自己负责的键，线性链下天然不冲突。
    query / correlation_id 由 10-api 注入初始 state，其余键由对应节点写入。
    """
    query: str                  # 用户问题（贯穿全链）
    correlation_id: str         # 关联 ID（= task id，10-api 生成）
    intent: str                 # router 分类出的意图（一句话）
    categories: list[str]       # router 判出的类别（Category.value）
    plan: list[dict[str, Any]]  # planner 产出的步骤序列 [{tool, args}]
    steps: list[dict[str, Any]]  # executor 每步结果 [{tool, status, result}]（status="completed"；失败整体上抛，见决策 5）
    report: str                 # reporter 最终报告（markdown，纯文本）
