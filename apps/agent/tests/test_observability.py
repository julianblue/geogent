"""Tests for the LangSmith startup diagnostics."""

import logging

import pytest

import geogent_agent.observability as observability
from geogent_agent.config import get_settings


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """The observability log is one-shot per process; reset it between tests."""
    observability._LOGGED = False
    get_settings.cache_clear()
    yield
    observability._LOGGED = False
    get_settings.cache_clear()


def test_logs_disabled_when_tracing_unset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    with caplog.at_level(logging.INFO, logger="geogent_agent.observability"):
        observability.configure_langsmith()
    assert any("disabled" in r.message for r in caplog.records)


def test_warns_when_tracing_enabled_but_key_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger="geogent_agent.observability"):
        observability.configure_langsmith()
    assert any("LANGSMITH_API_KEY is unset" in r.message for r in caplog.records)


def test_logs_enabled_with_project_and_endpoint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-test")
    monkeypatch.setenv("LANGSMITH_PROJECT", "geogent-test")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.smith.langchain.com")
    with caplog.at_level(logging.INFO, logger="geogent_agent.observability"):
        observability.configure_langsmith()
    assert any(
        "enabled" in r.message
        and "project=geogent-test" in r.message
        and "endpoint=https://eu.smith.langchain.com" in r.message
        for r in caplog.records
    )


def test_idempotent_under_repeated_calls(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LangGraph dev reloads modules; the status line must not spam."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    with caplog.at_level(logging.INFO, logger="geogent_agent.observability"):
        observability.configure_langsmith()
        observability.configure_langsmith()
        observability.configure_langsmith()
    assert sum(1 for r in caplog.records if "tracing" in r.message.lower()) == 1
