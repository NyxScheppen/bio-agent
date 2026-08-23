# LLM 统一客户端

> 范围：`backend/bioagent/llm/client.py`（`LlmClient` + `LlmMessage`），LangChain 统一调用、默认 Deepseek、token 抽取、模型名随调用记录、可注入 mock。全项目唯一 LLM 出口。
> 客户端 + 记账 spec：做「调 LLM → 记 `token_usage` 一行（best-effort）→ 返回 `LLMOutput`」，不含 Facade、不含 DDL、不含 API。
> `LlmClient` / `LlmMessage` 定义内联在本文件；`LLMOutput` / `TokenUsageDict` 取自 01-types、`LlmConfig` / `ConfigError` 取自 02-config、`Database` 取自 03-db（见前置依赖）。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types（`LLMOutput`、`TokenUsageDict`）、02-config（`LlmConfig`、`ConfigError`）、03-db（`Database`，记 `token_usage` 用）

## 用户故事

> 作为 bio agent 系统的开发者，我想要全项目唯一的 LLM 调用出口——统一走 LangChain、默认 Deepseek、每次调用自动抽取 token 用量和模型名、测试可注入 mock，以便 router/planner/executor/reporter 调 LLM 都走同一条路、token 与模型可查可追溯。

## 验收标准

- [ ] `client.py` 含 `LlmClient` + `LlmMessage`，与「`backend/bioagent/llm/client.py`（完整）」段代码逐字一致
- [ ] 全项目只有这一处直接调 LLM（不直接用 httpx、不绕过 client 直接 `ChatOpenAI`）
- [ ] `complete()` 返回 `LLMOutput`：`id` 每次调用唯一（uuid4）、`token_usage` 从 `usage_metadata` 抽取（缺失计 0）、`model` 随每次调用回填
- [ ] `complete()` 每次调用写一行 `token_usage`（`id`=output.id、`purpose`=output_type、`module`/`model`/token 用量照填）；写失败 best-effort（记日志不重抛，仍返回 `LLMOutput`）
- [ ] `json_mode=True` 时向模型传 `response_format={"type": "json_object"}`
- [ ] `LlmClient(model=..., model_name=..., db=...)` 可注入 fake model + fake db，测试不触网
- [ ] `pyright` strict 零报错
- [ ] api key 不进代码：`from_config` 用 `os.environ.get(api_key_env)` 读，未设报 `ConfigError`

## 技术方案

- **新文件**：`backend/bioagent/llm/client.py`（无 Facade、无 API；写 `token_usage` 表）
- **库**：`langchain_core`（`BaseChatModel` / 消息类）、`langchain_openai`（`ChatOpenAI`，deepseek / openai / ollama 等走 OpenAI 兼容接口）
- **公开面**：`from bioagent.llm.client import LlmClient, LlmMessage`（不加 `__all__`）
- **内部类（非 Facade）**：编排节点（09-orchestration）与评测 judge（08-eval）都通过它调 LLM，是透明化+可追溯的落点
- **落库（本 spec 自己写）**：`complete()` 每次调用写一行 `token_usage`（`id`=output.id、`correlation_id`、`module`、`purpose`=output_type、`model`、token 用量、`created_at`），**best-effort**（写失败记日志、照常返回 `LLMOutput`，记账是观测、主流程正确性不依赖它——见 CLAUDE.md 观测豁免）。eval 只产 `EvalReport` 分数、不再写 token_usage（见 08-eval）
- **多 provider（OpenAI 兼容）**：`from_config` 用 `_resolve_base_url(provider, base_url)` 解析 endpoint——显式 `llm.base_url` 优先，否则查内置映射（deepseek / openai / ollama）；无命中报 `ConfigError`（列出内置 provider + 提示配 `llm.base_url`）。统一走 `ChatOpenAI`，token 抽取不变
- **不设超时/重试**：LangChain 默认，异常原样上抛由调用方处理
- **json_mode = 减少 parse 失败重试**：router 意图分类 / planner 规划 / reporter 结构化输出都要 JSON，靠 `response_format` 保证合法 JSON，少一次重调
- **依赖 pin（实现时锁）**：`pyproject.toml` 里 `langchain-core`、`langchain-openai` 锁精确版本（非 `>=` 宽范围）；`pydantic` 用 `>=2.0` floor。本 spec 的 `usage_metadata`（键 `input_tokens`/`output_tokens`）、`AIMessage.content`（文本为 `str`）、`response_format={"type":"json_object"}` 契约均以锁定版本为准，升级依赖须重跑本 spec 测试
- **类型收窄（质量门驱动）**：`_extract_usage` 里 `isinstance(usage, dict)` 把 `getattr` 返回的 `Any` 收窄成 `dict[Unknown, Unknown]`，赋给 `dict[str, Any]` 报 partially unknown，故 `cast(dict[str, Any], usage)`（与 02-config `_build` 同模式）；`from_config` 里 `api_key` 用 `SecretStr(api_key)` 包装——langchain-openai 的 `api_key` 别名类型是 `SecretStr | Callable | None`，plain `str` 不满足 pyright strict，`SecretStr` 顺带让密钥不进 repr/日志

### `backend/bioagent/llm/client.py`（完整）

```python
import logging
import os
import time
import uuid
from typing import Any, Literal, TypedDict, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from bioagent.config import ConfigError, LlmConfig
from bioagent.db import Database
from bioagent.types import LLMOutput, TokenUsageDict

log = logging.getLogger(__name__)


# role 是 LLM 消息角色（system/user/assistant），与 01-types 的 Message 无关
class LlmMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


def _to_lc(m: LlmMessage) -> BaseMessage:
    """LlmMessage → LangChain 消息；纯函数，可单测。"""
    role = m["role"]
    if role == "system":
        return SystemMessage(content=m["content"])
    if role == "user":
        return HumanMessage(content=m["content"])
    if role == "assistant":
        return AIMessage(content=m["content"])
    raise ValueError(f"未知消息角色 {role!r}")   # 静态 Literal 已挡，此为运行期防御


def _safe_int(value: Any) -> int:
    """防御性转 int：非法值（None/非数字字符串/对象）计 0，不抛。纯函数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_usage(response: BaseMessage) -> TokenUsageDict:
    """从 LangChain 响应抽取 token 用量；兼容 dict 与 Pydantic 两种形状。"""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        data: dict[str, Any] = {}
    elif hasattr(usage, "model_dump"):    # Pydantic v2（langchain-core 用 v2）
        data = usage.model_dump()
    elif isinstance(usage, dict):
        data = cast(dict[str, Any], usage)
    else:
        data = {}                          # 未知形状：不静默猜，计 0 待查
    return {
        "input": _safe_int(data.get("input_tokens") or 0),   # 键缺失/值 None/非法 计 0
        "output": _safe_int(data.get("output_tokens") or 0),
    }


# 内置 provider → OpenAI 兼容 base_url；不在表内者配 llm.base_url 覆盖
_PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
}


def _resolve_base_url(provider: str, base_url: str | None) -> str | None:
    """provider → base_url：显式 base_url 优先，否则查内置映射；无命中 None。纯函数。"""
    if base_url:
        return base_url
    return _PROVIDER_BASE_URLS.get(provider)


class LlmClient:
    """全项目唯一 LLM 出口。持有 LangChain model 与 model 名，负责调用与 token 抽取。"""

    def __init__(self, model: BaseChatModel, model_name: str, db: Database) -> None:
        self._model = model
        self._model_name = model_name
        self._db = db
        # 显式传，不依赖 LangChain 的 model_name 属性（fake 未必有）

    @classmethod
    def from_config(cls, config: LlmConfig, db: Database) -> "LlmClient":
        base_url = _resolve_base_url(config.provider, config.base_url)
        if base_url is None:
            raise ConfigError(
                f"未知 provider={config.provider!r}：请设置 llm.base_url，"
                f"或使用内置 provider：{sorted(_PROVIDER_BASE_URLS)}"
            )
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise ConfigError(f"环境变量 {config.api_key_env} 未设置")
        return cls(
            ChatOpenAI(
                model=config.model,
                api_key=SecretStr(api_key),
                base_url=base_url,
            ),
            model_name=config.model,
            db=db,
        )

    async def complete(
        self,
        messages: list[LlmMessage],
        *,
        module: str,
        output_type: str,
        correlation_id: str,
        json_mode: bool = False,
    ) -> LLMOutput:
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self._model.ainvoke([_to_lc(m) for m in messages], **kwargs)
        content = response.content
        if not isinstance(content, str):
            raise RuntimeError(f"期望文本 content，得到 {type(content).__name__}")
        output = LLMOutput(
            id=str(uuid.uuid4()),    # 每次调用唯一，供 EvalReport.output_id
            module=module,           # router / planner / reporter / eval
            type=output_type,        # intent / plan / report / eval（→ TokenUsage.purpose）
            model=self._model_name,  # 模型名随每次调用记录，供 TokenUsage.model
            content=content,
            token_usage=_extract_usage(response),
            correlation_id=correlation_id,
        )
        await self._record_usage(output)   # best-effort：记账失败不阻断主流程
        return output

    async def _record_usage(self, output: LLMOutput) -> None:
        """写 token_usage 一行；best-effort（记账是观测，失败不阻断主流程，见 CLAUDE.md 豁免）。"""
        try:
            async with self._db.lock:
                await self._db.conn.execute(
                    "INSERT INTO token_usage (id, correlation_id, module, purpose, model, "
                    "input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        output.id,
                        output.correlation_id,
                        output.module,
                        output.type,
                        output.model,
                        output.token_usage["input"],
                        output.token_usage["output"],
                        time.time(),
                    ),
                )
                await self._db.conn.commit()
        except Exception:   # best-effort：观测豁免，失败只记日志不重抛
            log.warning("token_usage 记账失败（best-effort，不阻断主流程）：%s", output.id, exc_info=True)
```

## 测试要点

- [ ] 单元测试 `tests/test_llm/`：
  - [ ] `_to_lc` 纯函数：`system`→`SystemMessage`、`user`→`HumanMessage`、`assistant`→`AIMessage`，`content` 透传；非法 role → `ValueError`
  - [ ] `_extract_usage` 纯函数：dict 形状 `{input_tokens: 12, output_tokens: 7}` → `{input: 12, output: 7}`；Pydantic v2 形状（`model_dump()` 返回同键 dict）→ 同上；`usage_metadata` 为 `None` → `{input: 0, output: 0}`；键存在但值为 `None` → `{input: 0, output: 0}`；键值为非数字字符串（如 `input_tokens="abc"`）→ `{input: 0, ...}` 不抛；未知形状（无 `model_dump` 非 dict）→ `{input: 0, output: 0}`
  - [ ] `complete`（注入 fake `BaseChatModel`：`ainvoke` 返回预设 `AIMessage`，记录消息与 kwargs）：
    - [ ] `id`（非空 uuid）/`module`/`type`/`correlation_id`/`content` 正确回填进 `LLMOutput`
    - [ ] `model` 回填：`LlmClient(fake, "test-model", fake_db)` → `LLMOutput.model == "test-model"`
    - [ ] `token_usage` 抽取：`usage_metadata={input_tokens: 12, output_tokens: 7}` → `{input: 12, output: 7}`
    - [ ] `usage_metadata` 缺失 → `{input: 0, output: 0}`
    - [ ] `json_mode=True` → 传给模型的 kwargs 含 `response_format={"type": "json_object"}`；`False` → 不含
    - [ ] `messages` 顺序与内容按原序透传（fake 记录收到的 LangChain 消息）
    - [ ] 非文本 content（fake 返回 `content=list`）→ `RuntimeError`（不是 `str(list)` 的 repr 垃圾）
    - [ ] `token_usage` 行写入（fake db：`conn.execute` 记录 SQL 参数、`commit` 计数）：`complete()` 后 fake db 收到 1 条 `INSERT INTO token_usage`，`id==output.id`、`purpose==output_type`、`module`/`model`/token 用量正确
    - [ ] 记账失败 best-effort：fake db 的 `execute` 抛异常 → `complete()` 仍返回 `LLMOutput`（不重抛），记日志
  - [ ] `_resolve_base_url` 纯函数：显式 `base_url` 优先 / 已知 provider 命中 / 未知 provider 返回 `None`
  - [ ] `from_config`（`monkeypatch` 环境变量 + 注入 fake `Database`）：`provider="claude"`（无 base_url）→ `ConfigError`；`api_key_env` 未设（`delenv`）→ `ConfigError`；正常 → 返回 `LlmClient` 且 `_model_name == config.model`（`setenv` 设 key）；`provider="openai"` → 正常返回；自定义 `base_url` → 正常返回
- [ ] 集成测试：无（`LlmClient` 是内部类，无 Facade 管道；不测真实 LLM）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 后续编排节点 / RAG 调 LLM 都经 `LlmClient`（无绕过）；`token_usage` + `model` 产出为 08-eval 落库提供完整数据源
