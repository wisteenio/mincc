"""LLM provider 构建参数测试。"""

from __future__ import annotations

from mincc.config import Config
from mincc.llm import build_chat_model


def test_deepseek_disables_thinking_via_extra_body(monkeypatch) -> None:
    seen: dict = {}

    def fake_init_chat_model(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("mincc.llm.init_chat_model", fake_init_chat_model)

    build_chat_model(
        Config(
            llm_provider="deepseek",
            llm_model="deepseek-v4-pro",
            llm_api_key="test-key",
            llm_base_url=None,
            llm_temperature=0,
            llm_max_tokens=4096,
            llm_disable_thinking=True,
        )
    )

    assert seen["model_provider"] == "openai"
    assert seen["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_can_leave_thinking_enabled(monkeypatch) -> None:
    seen: dict = {}

    def fake_init_chat_model(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("mincc.llm.init_chat_model", fake_init_chat_model)

    build_chat_model(
        Config(
            llm_provider="deepseek",
            llm_model="deepseek-v4-pro",
            llm_api_key="test-key",
            llm_base_url=None,
            llm_temperature=0,
            llm_max_tokens=4096,
            llm_disable_thinking=False,
        )
    )

    assert "extra_body" not in seen
