"""LLM Provider 抽象：支持 anthropic、openai（含 OpenAI 兼容的国内/自部署模型）。

使用 langchain 的 init_chat_model 工厂统一构建，对外暴露 BaseChatModel。
未来要扩展 ollama / google / 自定义协议时，在 build_chat_model 内加一个分支即可。
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from mincc.config import Config


def build_chat_model(config: Config) -> BaseChatModel:
    provider = config.llm_provider

    if provider == "anthropic":
        return init_chat_model(
            model=config.llm_model,
            model_provider="anthropic",
            api_key=config.llm_api_key,
            temperature=config.llm_temperature,
        )

    if provider == "openai":
        # 国内模型 / 自部署模型走 OpenAI 兼容接口时也走这里，靠 base_url 区分
        kwargs: dict = {
            "model": config.llm_model,
            "model_provider": "openai",
            "api_key": config.llm_api_key,
            "temperature": config.llm_temperature,
        }
        if config.llm_base_url:
            kwargs["base_url"] = config.llm_base_url
        return init_chat_model(**kwargs)

    raise ValueError(
        f"暂不支持的 LLM_PROVIDER: {provider!r}；当前支持 anthropic、openai"
    )
