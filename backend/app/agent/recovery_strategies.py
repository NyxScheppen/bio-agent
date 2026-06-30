"""
统一工具恢复/重试策略系统 (Feature 3: Retry Strategies).

将 executor_agent.py 中硬编码的自动恢复逻辑抽象为可扩展的策略模式。

架构:
    RecoveryStrategy (ABC)
        ├── REnvironmentRecovery   — R 环境错误 → scan_system_config
        └── FileParseRecovery      — 文件解析错误 → probe_unknown_file

用法:
    # 全局默认（所有工具自动应用）
    from app.agent.recovery_strategies import DEFAULT_RECOVERY_STRATEGIES

    # 工具级自定义（注册时指定）
    @register_tool(
        name="my_tool",
        recovery_strategies=[MyCustomRecovery()],
        ...
    )
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class RecoveryStrategy(ABC):
    """
    工具恢复策略抽象基类。

    定义：
    1. matches()     — 判断是否触发
    2. get_recovery_tool_and_args() — 获取恢复操作
    3. max_retries   — 单次工具调用最多重试次数
    4. strategy_name — 人类可读标识
    """

    @abstractmethod
    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        """返回 True 表示当前错误匹配此策略。"""
        ...

    @abstractmethod
    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        """
        返回 (recovery_tool_name, recovery_args)。
        返回 (None, None) 表示无可执行恢复操作（如缺少文件路径）。
        """
        ...

    @property
    @abstractmethod
    def max_retries(self) -> int:
        """单次工具调用最大重试次数。"""
        ...

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """人类可读的策略名，用于日志。"""
        ...

    @staticmethod
    def _coerce_to_text(result: Any) -> str:
        """将任意 ToolResult 转为纯文本用于关键词匹配。"""
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, default=str)
        return str(result)


# ============================================================
# R 环境错误恢复
# ============================================================

class REnvironmentRecovery(RecoveryStrategy):
    """
    检测到 R 相关错误时，自动调用 scan_system_config 诊断后端环境。

    触发条件：结果文本包含 Rscript / package / library 错误关键词。
    恢复动作：调用 scan_system_config() 获取完整环境诊断。
    """

    _ERROR_KEYWORDS = [
        "rscript",
        "rscript.exe",
        "rscript not found",
        "找不到 r",
        "找不到r",
        "there is no package",
        "package",
        "library(",
        "r execution",
        "r 执行",
        "r环境",
        "r 环境",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        # 不要对 scan_system_config 自身递归
        if tool_name == "scan_system_config":
            return False
        text = self._coerce_to_text(tool_result).lower()
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        return ("scan_system_config", {})

    @property
    def max_retries(self) -> int:
        return 1

    @property
    def strategy_name(self) -> str:
        return "R环境自动恢复"


# ============================================================
# 文件解析错误恢复
# ============================================================

class FileParseRecovery(RecoveryStrategy):
    """
    检测到文件读入/解析错误时，自动调用 probe_unknown_file 探测文件格式。

    触发条件：结果文本包含 file not found / parse / encoding 等关键词。
    恢复动作：从原工具有参数中提取文件路径，调用 probe_unknown_file() 探测。
    """

    _ERROR_KEYWORDS = [
        "文件不存在",
        "no such file",
        "cannot open",
        "无法读取",
        "读取失败",
        "parse",
        "delimiter",
        "encoding",
        "格式",
        "not a valid",
        "缺少列",
        "missing column",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        # 不要对 probe_unknown_file 自身递归
        if tool_name == "probe_unknown_file":
            return False
        text = self._coerce_to_text(tool_result).lower()
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        file_path = self._guess_file_arg(function_args)
        if not file_path:
            return (None, None)
        return ("probe_unknown_file", {"file_path": file_path})

    @staticmethod
    def _guess_file_arg(function_args: Dict[str, Any]) -> str:
        """从工具有参数中推测文件路径。"""
        if not isinstance(function_args, dict):
            return ""

        preferred_keys = [
            "file_path",
            "expression_file",
            "count_file",
            "group_file",
            "input_file",
            "data_file",
        ]

        for k in preferred_keys:
            v = function_args.get(k)
            if isinstance(v, str) and v:
                return v

        # 兜底：查找任何以已知扩展名结尾的值
        known_exts = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".gz", ".zip")
        for _, v in function_args.items():
            if isinstance(v, str) and any(
                v.lower().endswith(x) for x in known_exts
            ):
                return v

        return ""

    @property
    def max_retries(self) -> int:
        return 2

    @property
    def strategy_name(self) -> str:
        return "文件解析自动恢复"


# ============================================================
# Phase 4.2: 超时恢复
# ============================================================

class TimeoutRecovery(RecoveryStrategy):
    """
    工具超时后，建议用更小的数据/参数重试或降级处理。

    触发条件：结果文本包含 timeout / 超时 关键词。
    恢复动作：无自动恢复（需要人工判断是否重试），但会给出明确建议。
    """

    _ERROR_KEYWORDS = [
        "timeout",
        "超时",
        "timed out",
        "timedout",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        text = self._coerce_to_text(tool_result).lower()
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        # 超时不自动重试（避免无限等待），但返回建议提示
        return (None, None)

    @property
    def max_retries(self) -> int:
        return 0  # 不自动重试

    @property
    def strategy_name(self) -> str:
        return "超时降级"


# ============================================================
# Phase 4.2: 缺失列恢复
# ============================================================

class ColumnMissingRecovery(RecoveryStrategy):
    """
    检测到 "missing column" 错误时，自动调用 preview_table_file 列出真实列名。

    触发条件：结果文本包含 missing column / 找不到列 / 列不存在 关键词。
    恢复动作：尝试调用同一文件上的 preview_table_file。
    """

    _ERROR_KEYWORDS = [
        "missing column",
        "column",
        "缺少列",
        "找不到列",
        "列不存在",
        "列名",
        "no column",
        "unknown column",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        if tool_name == "preview_table_file":
            return False
        text = self._coerce_to_text(tool_result).lower()
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        file_path = FileParseRecovery._guess_file_arg(function_args)
        if not file_path:
            return (None, None)
        return ("preview_table_file", {"file_path": file_path, "nrows": 5})

    @property
    def max_retries(self) -> int:
        return 1

    @property
    def strategy_name(self) -> str:
        return "列名自动探测"


# ============================================================
# Phase 4.2: R 包缺失恢复
# ============================================================

class DependencyRecovery(RecoveryStrategy):
    """
    检测到 "there is no package" 错误时，调用 scan_system_config 诊断 R 环境。

    触发条件：结果文本包含 package / library / namespace 缺失关键词。
    恢复动作：调用 scan_system_config() 获取已安装包列表。
    """

    _ERROR_KEYWORDS = [
        "there is no package called",
        "namespace",
        "could not find function",
        "is not available",
        "package",
        "library",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        if tool_name == "scan_system_config":
            return False
        text = self._coerce_to_text(tool_result).lower()
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        return ("scan_system_config", {})

    @property
    def max_retries(self) -> int:
        return 1

    @property
    def strategy_name(self) -> str:
        return "R包依赖诊断"


# ============================================================
# Phase 4.2: 编码错误恢复
# ============================================================

class EncodingRecovery(RecoveryStrategy):
    """
    检测到 encoding 错误时，调用 probe_unknown_file 以探测正确编码。

    触发条件：结果文本包含 encoding / UnicodeDecode / 乱码关键词。
    恢复动作：调用 probe_unknown_file() 探测编码和格式。
    """

    _ERROR_KEYWORDS = [
        "encoding",
        "unicodedecode",
        "codec",
        "decode",
        "编码",
        "乱码",
        "utf",
        "gbk",
        "latin",
        "ascii",
    ]

    def matches(
        self,
        tool_result: Any,
        tool_name: str,
        function_args: Dict[str, Any],
    ) -> bool:
        if tool_name == "probe_unknown_file":
            return False
        text = self._coerce_to_text(tool_result).lower()
        # 避免误匹配：只在明确是错误时触发
        has_error = any(k in text for k in [
            "decode", "encoding", "codec"
        ])
        if not has_error:
            return False
        return any(k in text for k in self._ERROR_KEYWORDS)

    def get_recovery_tool_and_args(
        self,
        function_args: Dict[str, Any],
    ) -> tuple:
        file_path = FileParseRecovery._guess_file_arg(function_args)
        if not file_path:
            return (None, None)
        return ("probe_unknown_file", {"file_path": file_path})

    @property
    def max_retries(self) -> int:
        return 1

    @property
    def strategy_name(self) -> str:
        return "编码自动探测"


# ============================================================
# 全局默认策略列表
# ============================================================

DEFAULT_RECOVERY_STRATEGIES: List[RecoveryStrategy] = [
    REnvironmentRecovery(),
    FileParseRecovery(),
    TimeoutRecovery(),
    ColumnMissingRecovery(),
    DependencyRecovery(),
    EncodingRecovery(),
]
