# 配置加载

> 范围：`backend/bioagent/config.py`（`Config` + 6 个分段 dataclass + `load_config()` + `validate_config()` + `ConfigError`）+ `config.yaml`。
> 纯配置 spec：只做加载与校验，不含 Facade、不含 DDL、不含 API。
> **本文件自包含**：`config.yaml` 与 `config.py` 的完整定义都内联在下文，实现不依赖任何其它文档。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **CWD 约定**：`config.yaml` 与所有相对路径（`db.db_path`、`storage.upload_dir`、`storage.r_scripts_dir`）均以**仓库根**为 CWD，进程须从仓库根启动——否则 `config.yaml` 找不到、`backend/bioagent/r_scripts` 会误解析成 `backend/backend/bioagent/r_scripts`
- **前置依赖**：无（配置项内联在本文件）

## 用户故事

> 作为 bio agent 系统的开发者，我想要一份启动时同步加载、带默认值、类型安全、错配即报的配置对象，以便各模块用 `config.llm.model` 这种点号访问读参数。

## 验收标准

- [ ] `config.py` 含 `Config` + 6 分段 dataclass，字段与「`backend/bioagent/config.py`（完整）」段代码逐字一致
- [ ] `load_config()` 同步返回 `Config`；缺键填默认值、未知键（含嵌套段内部）报 `ConfigError`
- [ ] `validate_config()` 是纯函数，逐字段校验，非法报 `ConfigError`
- [ ] `pyright` strict 下零报错
- [ ] 秘密不进 yaml：`llm.api_key_env` 只存环境变量名，key 本体由 04-llm 构造时读 `os.environ`

## 技术方案

- **新文件**：`backend/bioagent/config.py`、`config.yaml`（无 Facade、无 API、无数据变更）
- **库**：PyYAML（`yaml.safe_load`）
- **公开面**：`from bioagent.config import Config, load_config, validate_config`（不加 `__all__`；`ConfigError` 与各分段 dataclass 如 `LlmConfig` 也直接可导，04-llm 会 import）
- **同步加载**（启动时一次性，event loop 未起，非运行期 I/O）
- **递归构造**：`_build` 看到字段类型是 dataclass 就递归构造，所以嵌套段会变成对应 dataclass
- **类型标注**：`_build` 用 `Any`（`dc: Any, raw: Any -> Any`）而非泛型 `_T`——`dataclasses.Field.type` 与 `yaml.safe_load` 都返回 `Any`，pyright strict 下 `type[_T]` 不满足 `DataclassInstance` 协议、返回类型无法静态验证。用 `Any` + `cast(dict[str, Any], raw)` 诚实承认反射构造是动态的，不假装类型精确。
- **缺文件即报错**：`config.yaml` 缺失 → `ConfigError`（错误可溯源；"用全默认值"的场景由「缺键」覆盖，不靠「缺文件」）

### config.yaml（完整）

```yaml
llm:
  provider: deepseek          # deepseek | openai | ollama（04-llm 内置映射键）；校验只查非空，未知 provider 由 04-llm 构造时报错——其它 OpenAI 兼容服务配 base_url 即可
  model: deepseek-chat
  api_key_env: DEEPSEEK_API_KEY
  # base_url: http://localhost:11434/v1   # 可选：覆盖/自定义 endpoint

embedding:
  model: all-MiniLM-L6-v2     # 本地 sentence-transformers（07-rag 向量化）

db:
  db_path: data/bioagent.db    # SQLite 文件路径（03-db）

storage:
  upload_dir: data/uploads     # 上传文件落盘目录（10-api，uuid 重命名）
  r_scripts_dir: backend/bioagent/r_scripts  # 服务端 R 脚本目录（06-r-runner）

rag:
  qdrant_url: http://localhost:6333
  collection: bioagent_kb      # Qdrant collection 名
  top_k: 5                     # 检索返回条数

eval:
  judge_sample_rate: 0.1       # LLM-judge 抽样比例
```

### backend/bioagent/config.py（完整）

```python
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, cast

import yaml


class ConfigError(Exception):
    """配置加载或校验失败。"""


@dataclass
class LlmConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"  # 存环境变量名，key 本体由 04-llm 读
    base_url: str | None = None            # 可选 endpoint 覆盖；缺省查 provider 映射（映射表在 04-llm，本 spec 不定义）


@dataclass
class EmbeddingConfig:
    model: str = "all-MiniLM-L6-v2"


@dataclass
class DbConfig:
    db_path: str = "data/bioagent.db"


@dataclass
class StorageConfig:
    upload_dir: str = "data/uploads"
    r_scripts_dir: str = "backend/bioagent/r_scripts"


@dataclass
class RagConfig:
    qdrant_url: str = "http://localhost:6333"
    collection: str = "bioagent_kb"
    top_k: int = 5


@dataclass
class EvalConfig:
    judge_sample_rate: float = 0.1


@dataclass
class Config:
    llm: LlmConfig = field(default_factory=LlmConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    db: DbConfig = field(default_factory=DbConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)


def _build(dc: Any, raw: Any) -> Any:
    """按 dataclass 字段递归构造：未知键报错、缺键用默认值、嵌套 dataclass 字段递归。"""
    if not isinstance(raw, dict):
        raise ConfigError(f"{dc.__name__} 必须是映射")
    data = cast(dict[str, Any], raw)
    unknown = set(data) - {f.name for f in fields(dc)}
    if unknown:
        # key=str：YAML 键类型可混合（1:/true:/日期），默认排序会 TypeError
        raise ConfigError(f"未知配置键 {sorted(unknown, key=str)} in {dc.__name__}")
    kwargs: dict[str, Any] = {}
    for f in fields(dc):
        if f.name not in data:
            continue  # 缺键用 dataclass 默认值
        value = data[f.name]
        # f.type 是字段注解（无 from __future__ import annotations，故为实际类）
        if is_dataclass(f.type):
            if not isinstance(value, dict):
                raise ConfigError(
                    f"{dc.__name__}.{f.name} 必须是映射，得到 {type(value).__name__}"
                )
            value = _build(f.type, value)  # 嵌套 dataclass 递归构造
        kwargs[f.name] = value
    return dc(**kwargs)


def load_config(path: str | None = None) -> Config:
    # 1) 解析路径：显式 path > BIOAGENT_CONFIG 环境变量 > 默认 "config.yaml"
    resolved = path or os.environ.get("BIOAGENT_CONFIG") or "config.yaml"
    try:
        raw: Any = yaml.safe_load(Path(resolved).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ConfigError(f"配置加载失败 {resolved}: {exc}") from exc
    if raw is None:
        # 空文件/顶层 null → 空配置；falsy 标量（0/""/[]）仍交 _build 报「必须是映射」
        raw = {}
    # 2) 递归构造（未知键/嵌套 dataclass 由 _build 处理）
    cfg = _build(Config, raw)
    # 3) 范围校验
    validate_config(cfg)
    return cfg


def _nonempty(v: Any, path: str) -> None:
    if not isinstance(v, str) or not v:
        raise ConfigError(f"{path} 非法: {v!r}")


def _pos_int(v: Any, path: str) -> None:
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise ConfigError(f"{path} 非法: {v!r}")


def _unit_interval(v: Any, path: str) -> None:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= v <= 1.0):
        raise ConfigError(f"{path} 非法: {v!r}")


def validate_config(cfg: Config) -> None:
    # 非空 str
    _nonempty(cfg.llm.provider, "llm.provider")
    _nonempty(cfg.llm.model, "llm.model")
    _nonempty(cfg.llm.api_key_env, "llm.api_key_env")
    _nonempty(cfg.embedding.model, "embedding.model")
    _nonempty(cfg.db.db_path, "db.db_path")
    _nonempty(cfg.storage.upload_dir, "storage.upload_dir")
    _nonempty(cfg.storage.r_scripts_dir, "storage.r_scripts_dir")
    _nonempty(cfg.rag.qdrant_url, "rag.qdrant_url")
    _nonempty(cfg.rag.collection, "rag.collection")

    # 可选 str：None 放行（走 provider 映射，见 04-llm），非 None 时非空
    if cfg.llm.base_url is not None:
        _nonempty(cfg.llm.base_url, "llm.base_url")

    # int > 0
    _pos_int(cfg.rag.top_k, "rag.top_k")

    # 数 ∈ [0, 1]
    _unit_interval(cfg.eval.judge_sample_rate, "eval.judge_sample_rate")
```

**校验规则表**（`validate_config` 实现与此逐条对应）：

| 字段 | 约束 |
|---|---|
| `llm.provider` / `llm.model` / `llm.api_key_env` | 非空 `str` |
| `llm.base_url` | 非 `None` 时非空 `str`（`""` 静默回退映射 → 报错） |
| `embedding.model` | 非空 `str` |
| `db.db_path` | 非空 `str` |
| `storage.upload_dir` / `storage.r_scripts_dir` | 非空 `str` |
| `rag.qdrant_url` / `rag.collection` | 非空 `str` |
| `rag.top_k` | `int > 0` |
| `eval.judge_sample_rate` | 数 ∈ `[0, 1]` |

## 测试要点

- [ ] 单元测试 `tests/test_config/`：
  - [ ] `validate_config` 纯函数：合法 `Config()` 通过；越界值（`judge_sample_rate=1.5`）报错；非正（`top_k=0`）报错；错类型（改字段为 `"20"` / `True`）报错；`base_url=None` 通过、`base_url=""` 报错（直接构造 `Config` 后改字段再调 `validate_config`）
  - [ ] `load_config`（tmp yaml + `monkeypatch` 环境变量）：
    - [ ] 缺键填默认（只写 `llm.provider` → 其余字段=默认）
    - [ ] 未知顶层键 / 段内键报 `ConfigError`
    - [ ] 嵌套 dataclass 字段给非 dict 值：`db: "data/bioagent.db"` → `ConfigError`（不是 `AttributeError`/`TypeError` 裸崩溃）
    - [ ] 文件缺失报 `ConfigError`
    - [ ] 坏 YAML 报 `ConfigError`
    - [ ] `BIOAGENT_CONFIG` 覆盖路径生效；`path=None` 时读 `config.yaml`
- [ ] 集成测试：无（无 Facade 管道）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `load_config()` 能从 `config.yaml`（或显式 path）拿到 `Config`，点号访问到 `config.rag.top_k`（组合根 `main.py` 归 10-api，本 spec 不创建）
