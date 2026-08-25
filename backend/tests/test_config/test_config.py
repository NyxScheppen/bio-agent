from pathlib import Path

import pytest

from bioagent.config import Config, ConfigError, load_config, validate_config


# ---- validate_config 纯函数 ----

def test_validate_config_default_valid() -> None:
    validate_config(Config())


def test_validate_config_judge_sample_rate_out_of_range() -> None:
    cfg = Config()
    cfg.eval.judge_sample_rate = 1.5
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_top_k_non_positive() -> None:
    cfg = Config()
    cfg.rag.top_k = 0
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_top_k_wrong_type_str() -> None:
    cfg = Config()
    setattr(cfg.rag, "top_k", "20")
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_top_k_wrong_type_bool() -> None:
    cfg = Config()
    setattr(cfg.rag, "top_k", True)
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_validate_config_base_url_none_ok() -> None:
    cfg = Config()
    cfg.llm.base_url = None
    validate_config(cfg)


def test_validate_config_base_url_empty_fails() -> None:
    cfg = Config()
    cfg.llm.base_url = ""
    with pytest.raises(ConfigError):
        validate_config(cfg)


# ---- load_config（tmp yaml + monkeypatch） ----

def test_load_config_missing_keys_fill_defaults(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("llm:\n  provider: openai\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.llm.provider == "openai"
    assert cfg.llm.model == "deepseek-chat"
    assert cfg.rag.top_k == 5


def test_load_config_unknown_top_level_key(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("nope: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_load_config_unknown_nested_key(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("llm:\n  bad_key: x\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_load_config_nested_not_mapping(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text('db: "data/bioagent.db"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(str(tmp_path / "missing.yaml"))


def test_load_config_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_load_config_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("llm:\n  model: gpt-4\n", encoding="utf-8")
    monkeypatch.setenv("BIOAGENT_CONFIG", str(p))
    assert load_config().llm.model == "gpt-4"


def test_load_config_default_path_reads_config_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BIOAGENT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "llm:\n  provider: ollama\n", encoding="utf-8"
    )
    assert load_config().llm.provider == "ollama"
