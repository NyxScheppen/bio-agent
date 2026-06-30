"""
工具自动发现模块。

自动扫描 app.tools 包下所有 .py 模块并触发工具注册。
跳过 __init__.py，支持递归子目录，避免重复注册。
"""

import importlib
import pkgutil
from pathlib import Path
from typing import List

from app.agent.tool_registry import _LOADED_TOOL_MODULES, TOOL_REGISTRY, TOOLS_SCHEMA


def auto_discover_tools(package_name: str = "app.tools") -> List[str]:
    """
    自动发现并导入指定包下的所有工具模块。

    递归扫描子包，跳过 __init__.py 和已加载模块。

    Args:
        package_name: 包全限定名，默认 "app.tools"

    Returns:
        成功加载的模块名列表
    """
    loaded: List[str] = []

    try:
        package = importlib.import_module(package_name)
    except ImportError as e:
        print(f"[tool_discovery] Cannot import {package_name}: {e}")
        return loaded

    # 获取包路径
    if hasattr(package, "__path__"):
        package_paths = list(package.__path__)
    else:
        # 回退：从 __file__ 推断
        pkg_file = getattr(package, "__file__", None)
        if pkg_file:
            package_paths = [str(Path(pkg_file).parent)]
        else:
            return loaded

    # 注册发现前的基准
    count_before = len(TOOL_REGISTRY)

    for package_path in package_paths:
        _discover_in_path(package_path, package_name, loaded)

    count_after = len(TOOL_REGISTRY)
    new_tools = count_after - count_before

    if new_tools > 0:
        print(
            f"[tool_discovery] Loaded {len(loaded)} modules, "
            f"registered {new_tools} new tools "
            f"(total: {count_after})"
        )
    else:
        print(
            f"[tool_discovery] Scanned {len(loaded)} modules, "
            f"no new tools (all {count_after} already registered)"
        )

    return loaded


def _discover_in_path(
    package_path: str,
    package_name: str,
    loaded: List[str],
):
    """在指定路径下递归发现工具模块。"""
    path = Path(package_path)
    if not path.exists() or not path.is_dir():
        return

    for entry in sorted(path.iterdir()):
        name = entry.name

        # 跳过隐藏文件/目录
        if name.startswith("_") and name != "__init__.py":
            continue

        if entry.is_dir():
            # 递归子包
            subpackage = f"{package_name}.{name}"
            if subpackage not in _LOADED_TOOL_MODULES:
                _LOADED_TOOL_MODULES.add(subpackage)
                try:
                    importlib.import_module(subpackage)
                    loaded.append(subpackage)
                except Exception as e:
                    print(f"[tool_discovery] Failed to import {subpackage}: {e}")

        elif entry.is_file() and name.endswith(".py") and name != "__init__.py":
            module_name = name[:-3]  # remove .py
            full_name = f"{package_name}.{module_name}"

            if full_name in _LOADED_TOOL_MODULES:
                continue

            _LOADED_TOOL_MODULES.add(full_name)
            try:
                importlib.import_module(full_name)
                loaded.append(full_name)
            except Exception as e:
                print(f"[tool_discovery] Failed to import {full_name}: {e}")


def list_discovered_tools() -> dict:
    """
    列出所有已注册工具的摘要。

    Returns:
        {tool_name: {category, schema_source, tags}}
    """
    from app.agent.tool_registry import TOOL_META

    result = {}
    for name, meta in sorted(TOOL_META.items()):
        result[name] = {
            "category": meta.get("category", "general"),
            "schema_source": meta.get("schema_source", "unknown"),
            "tags": meta.get("tags", []),
        }
    return result


def has_tool(name: str) -> bool:
    """检查工具是否已注册。"""
    return name in TOOL_REGISTRY
