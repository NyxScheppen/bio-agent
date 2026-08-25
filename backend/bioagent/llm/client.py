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


# role 是 LLM 消息角色（system/user/assistant）
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
        "input": _safe_int(data.get("input_tokens")),   # 键缺失/值 None/非法 计 0
        "output": _safe_int(data.get("output_tokens")),
    }


# 内置 provider → OpenAI 兼容 base_url；不在表内者配 llm.base_url 覆盖
_PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
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
        if not api_key and config.provider != "ollama":
            raise ConfigError(f"环境变量 {config.api_key_env} 未设置")
        api_key = api_key or "ollama"  # ollama 本地无鉴权：dummy 值仅满足 ChatOpenAI 非空约束
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
