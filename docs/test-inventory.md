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

### 02-config：配置加载

- **新增测试**：
  - `tests/test_config/test_config.py` — `validate_config` 纯函数测试（7 条）、`load_config` 测试（8 条，tmp yaml + monkeypatch）
- **检查方向**：
  - 功能正确：缺键填默认、`BIOAGENT_CONFIG` 覆盖路径、`path=None` 读 `config.yaml`；合法配置通过、`base_url=None` 放行
  - 边界鲁棒：未知顶层/段内键报错、嵌套段非 dict 报错、文件缺失/坏 YAML 报错、越界值（`judge_sample_rate=1.5` / `top_k=0`）报错、错类型（`"20"` / `True`）报错、`base_url=""` 报错
- **所属系统**：配置（`backend/bioagent/config.py` / `config.yaml`）
- **阶段**：spec 02-config 实现
