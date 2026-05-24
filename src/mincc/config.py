"""配置加载：从 .env 与环境变量读取运行时配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str | None
    llm_temperature: float


def load_config(env_file: str | Path | None = None) -> Config:
    """加载配置。env_file 为 None 时按 dotenv 默认行为查找 .env。"""
    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        load_dotenv(override=False)

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    temperature_raw = os.getenv("LLM_TEMPERATURE", "0").strip()

    if not model:
        raise ValueError("缺少 LLM_MODEL 环境变量，请在 .env 中配置")
    if not api_key:
        raise ValueError("缺少 LLM_API_KEY 环境变量，请在 .env 中配置")

    try:
        temperature = float(temperature_raw)
    except ValueError as exc:
        raise ValueError(f"LLM_TEMPERATURE 必须是数字，当前值：{temperature_raw!r}") from exc

    return Config(
        llm_provider=provider,
        llm_model=model,
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_temperature=temperature,
    )
