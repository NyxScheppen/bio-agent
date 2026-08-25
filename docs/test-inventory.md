# 测试清单

> 每次编写测试后追加条目。每条记录：新增了哪些测试 / 检查方向 / 所属系统 / 在哪个功能阶段编写。

## 条目

### 01-types：枚举 + 实体类型

- **新增测试**：
  - `tests/test_types/test_enums.py` — 3 个枚举穷尽断言、命名约定断言、StrEnum 序列化断言
  - `tests/test_types/test_types.py` — ToolDefinition 形状（Python/R 工具）、`default_factory` 隔离、TypedDict 键集合断言
- **检查方向**：
  - 功能正确：枚举值集合完整、值 = 成员名小写、`json.dumps` 直接序列化；dataclass 字段与默认值、TypedDict 键完整性
  - 回归保护：防枚举漏成员/多成员/改值；防 `frontend` 两次实例化共享
- **所属系统**：类型与枚举（`backend/bioagent/enums.py` / `types.py`）
- **阶段**：spec 01-types 实现
