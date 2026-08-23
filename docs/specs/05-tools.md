# 工具注册表 + 自动发现

> 范围：`backend/bioagent/tools/__init__.py`（`ToolRegistry`）。工具注册、pkgutil 自动发现、按类别裁剪。
> 纯基础设施 spec：只管「收集 ToolDefinition → 查询」，不含任何工具的具体实现（那是 11-15 spec 的活）、不含 Facade、不含 API。
> `ToolRegistry` 定义内联在本文件；`ToolDefinition` / `Category` 取自 01-types（见前置依赖）。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types（`ToolDefinition`、`Category`）

## 用户故事

> 作为 bio agent 系统的开发者，我想要「加工具 = 加一个文件」的注册机制——丢一个 `backend/bioagent/tools/<category>/<name>.py`（导出 `TOOL`）即自动被发现、按类别查询，以便扩展分析能力时不改任何注册代码。

## 验收标准

- [ ] `backend/bioagent/tools/__init__.py` 含 `ToolRegistry`，与「`backend/bioagent/tools/__init__.py`（完整）」段代码逐字一致
- [ ] `register()` 拒绝重名（`ValueError`）；`get()` 命中返回、未命中 `KeyError`
- [ ] `register()` 校验 runtime 契约：R 工具须 `r_script` 非空且 `run is None`，Python 工具须 `run` 非空且 `r_script is None`，违反报 `ValueError`
- [ ] `discover()` 递归 walk `bioagent.tools`，收集各模块导出的 `TOOL`（`isinstance(ToolDefinition)`）
- [ ] `for_categories()` 只返回指定类别的工具
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`backend/bioagent/tools/__init__.py`（无 Facade、无 API、无数据变更）
- **公开面**：`from bioagent.tools import ToolRegistry`（不加 `__all__`）
- **发现机制**：`pkgutil.walk_packages` 递归遍历 `bioagent.tools` 包（含 `<category>/` 子包），每个模块 `importlib.import_module` 后取 `TOOL` 属性，`isinstance(tool, ToolDefinition)` 才 `register`。子包（category 目录）用空 `__init__.py` 占位，不导出 `TOOL`，walk 自然跳过
- **为什么 pkgutil 而非手写清单**：「加工具 = 加文件」的承诺靠自动发现兑现——手写 `__all__`/注册表 = 每加工具改一处，违背目标
- **重名即错**：工具名是 plan 步骤 `{tool, args}` 里 executor 用 `registry.get(name)` 解析的键，重名无法区分；`register` 抛 `ValueError` 早暴露
- **类别裁剪是编排的入口**：`for_categories()` 供 09-orchestration 的 planner 用——router 判出的类别集合 → 只把对应工具清单放进规划 prompt，减少无关工具的干扰

### `backend/bioagent/tools/__init__.py`（完整）

```python
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
```

## 测试要点

- [ ] 单元测试 `tests/test_tools/`：
  - [ ] `register` / `get`：注册后 `get(name)` 返回同一实例；`get("nope")` → `KeyError`；重名 `register` → `ValueError`
  - [ ] `register` runtime 契约：R 工具 `r_script=None` → `ValueError`；R 工具 `r_script=""` → `ValueError`；R 工具 `run` 非空 → `ValueError`；Python 工具 `run=None` → `ValueError`；Python 工具带 `r_script` → `ValueError`；合规的 Python/R 工具正常注册
  - [ ] `for_categories`：注册 3 个工具（`Category.SINGLE_GENE` / `Category.DGE` / `Category.DGE`），`for_categories({Category.DGE})` 只返回 2 个 DGE 工具；空集合返回空
  - [ ] `all_tools` / `__iter__` / `__len__`：注册 N 个 → `len == N`、`all_tools()` 长度一致、迭代遍数一致
- [ ] 集成测试 `tests/test_tools/`（fixture 包）：
  - [ ] `discover`：在 `tests/fixtures/fake_tools/`（含 `dge_foo.py` 导出 `TOOL`、`__init__.py` 不导出、一个导出非 `ToolDefinition` 的 `JUNK` 模块）上 `discover("tests.fixtures.fake_tools")` → 只注册 `dge_foo` 的 `TOOL`，`JUNK` 被跳过
  - [ ] `discover` 非幂等（生产只调一次）：同一 registry 重复 `discover` 同一 package → 第二次 `register` 撞同名抛 `ValueError`（属预期，非幂等）；测试用空 registry 各跑一次覆盖发现正确性
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 后续工具（11-15）只需写 `backend/bioagent/tools/<category>/<name>.py` 导出 `TOOL`，`discover()` 自动纳入；09-orchestration 用 `for_categories` 给 planner 供工具
