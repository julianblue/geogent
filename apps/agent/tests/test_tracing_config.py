"""Tests for the LangSmith run-tagging helper."""

import pytest

from geogent_agent.config import get_settings
from geogent_agent.utils.tracing import build_tracing_config


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_tags_carry_architecture_provider_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODEL", "claude-sonnet-4-6")
    cfg = build_tracing_config({}, architecture="langgraph_react")
    assert set(cfg["tags"]) == {
        "architecture:langgraph_react",
        "provider:anthropic",
        "model:claude-sonnet-4-6",
    }
    assert cfg["metadata"]["provider"] == "anthropic"
    assert cfg["metadata"]["model"] == "claude-sonnet-4-6"
    assert cfg["run_name"] == "geogent.langgraph_react.agent"


def test_passthrough_ids_included_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODEL", "gpt-4o")
    cfg = build_tracing_config(
        {"thread_id": "t1", "assistant_id": "a1", "map_state": {}},
        architecture="classic_langchain",
    )
    assert cfg["metadata"]["thread_id"] == "t1"
    assert cfg["metadata"]["assistant_id"] == "a1"
    assert "map_state" not in cfg["metadata"]
    assert "user_id" not in cfg["metadata"]


def test_missing_ids_are_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODEL", "gpt-4o")
    cfg = build_tracing_config({}, architecture="classic_langchain")
    for key in ("thread_id", "assistant_id", "user_id"):
        assert key not in cfg["metadata"]
