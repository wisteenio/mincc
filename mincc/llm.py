"""LLM Provider 抽象：仅支持 claude、openai、deepseek。

使用 langchain 的 init_chat_model 工厂统一构建，对外暴露 BaseChatModel。
- claude   → anthropic 官方接口
- openai   → OpenAI 官方接口
- deepseek → OpenAI 兼容接口，默认端点 https://api.deepseek.com/v1
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from mincc.config import Config

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


def build_chat_model(config: Config) -> BaseChatModel:
    provider = config.llm_provider

    if provider == "claude":
        return init_chat_model(
            model=config.llm_model,
            model_provider="anthropic",
            api_key=config.llm_api_key,
            temperature=config.llm_temperature,
        )

    if provider == "openai":
        kwargs: dict = {
            "model": config.llm_model,
            "model_provider": "openai",
            "api_key": config.llm_api_key,
            "temperature": config.llm_temperature,
        }
        if config.llm_base_url:
            kwargs["base_url"] = config.llm_base_url
        return init_chat_model(**kwargs)

    if provider == "deepseek":
        return init_chat_model(
            model=config.llm_model,
            model_provider="openai",
            api_key=config.llm_api_key,
            base_url=config.llm_base_url or DEEPSEEK_DEFAULT_BASE_URL,
            temperature=config.llm_temperature,
        )

    raise ValueError(
        f"暂不支持的 LLM_PROVIDER: {provider!r}；当前支持 claude、openai、deepseek"
    )
