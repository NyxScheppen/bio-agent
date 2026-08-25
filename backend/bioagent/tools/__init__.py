import importlib
import pkgutil
from collections.abc import Iterator

from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


class ToolRegistry:
    """工具集合：注册 / 自动发现 / 按名与按类别查询。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        # 执行契约：R 工具只声明 r_script（run=None），Python 工具只声明 run（r_script=None）
        if tool.runtime is Runtime.R:
            if not tool.r_script or tool.run is not None:   # r_script 非空：None 与 "" 都拒绝
                raise ValueError(f"R 工具 {tool.name} 必须声明非空 r_script 且 run 为 None")
        elif tool.run is None or tool.r_script is not None:
            raise ValueError(f"Python 工具 {tool.name} 必须声明 run 且 r_script 为 None")
        self._tools[tool.name] = tool

    def discover(self, package: str = "bioagent.tools") -> None:
        """递归 import package 下所有模块，收集导出的 `TOOL`（ToolDefinition）。

        子包（<category>/）只有空 __init__.py，不导出 TOOL，walk 自动跳过。
        """
        pkg = importlib.import_module(package)
        for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=package + "."):
            module = importlib.import_module(mod_name)
            tool = getattr(module, "TOOL", None)
            if isinstance(tool, ToolDefinition):
                self.register(tool)

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]  # 未命中 KeyError

    def for_categories(self, categories: set[Category]) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.category in categories]

    def all_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def __iter__(self) -> Iterator[ToolDefinition]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
