"""配置加载测试。"""

import pytest

from mincc.config import DEFAULT_LLM_MAX_TOKENS, load_config


def test_load_config_uses_default_max_tokens(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)

    config = load_config()

    assert config.llm_max_tokens == DEFAULT_LLM_MAX_TOKENS
    assert config.llm_disable_thinking is False


def test_load_config_disables_thinking_by_default_for_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_DISABLE_THINKING", raising=False)

    config = load_config()

    assert config.llm_disable_thinking is True


def test_load_config_allows_thinking_override_for_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DISABLE_THINKING", "false")

    config = load_config()

    assert config.llm_disable_thinking is False


def test_load_config_rejects_invalid_disable_thinking(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DISABLE_THINKING", "sometimes")

    with pytest.raises(ValueError, match="LLM_DISABLE_THINKING 必须是布尔值"):
        load_config()


def test_load_config_reads_max_tokens(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_TOKENS", "8192")

    config = load_config()

    assert config.llm_max_tokens == 8192


def test_load_config_rejects_invalid_max_tokens(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_TOKENS", "0")

    with pytest.raises(ValueError, match="LLM_MAX_TOKENS 必须大于 0"):
        load_config()
