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


class _UniqueKeyLoader(yaml.SafeLoader):
    """拒绝重复键的 SafeLoader：默认 SafeLoader 对重复键静默 last-wins。"""


def _construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigError(f"重复配置键 {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_config(path: str | None = None) -> Config:
    # 1) 解析路径：显式 path > BIOAGENT_CONFIG 环境变量 > 默认 "config.yaml"
    resolved = path or os.environ.get("BIOAGENT_CONFIG") or "config.yaml"
    try:
        raw: Any = yaml.load(Path(resolved).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
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
