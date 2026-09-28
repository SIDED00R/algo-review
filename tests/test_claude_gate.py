"""LLM 제공자 선택 — 토큰이 있으면 Claude 를 쓰고, 어떤 실패든 None 으로 폴백한다."""
import pytest

import claude_gate
from claude_client import ClaudeUnavailable


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(claude_gate.claude_client, "is_configured", lambda: True)


def test_without_token_skips_claude(monkeypatch):
    def _complete_must_not_run(*_):
        raise AssertionError("Claude 를 부르면 안 된다")

    monkeypatch.setattr(claude_gate.claude_client, "is_configured", lambda: False)
    monkeypatch.setattr(claude_gate.claude_client, "complete", _complete_must_not_run)
    assert claude_gate.claude_answer("s", "u") is None


def test_configured_gets_the_claude_answer(monkeypatch, configured):
    monkeypatch.setattr(claude_gate.claude_client, "complete", lambda s, u: f"{s}|{u}")
    assert claude_gate.claude_answer("s", "u") == "s|u"


@pytest.mark.parametrize("error", [ClaudeUnavailable("assistant error: rate_limit"), RuntimeError("CLI 죽음")])
def test_any_claude_failure_falls_back_with_a_warning(monkeypatch, configured, caplog, error):
    def _fail(*_):
        raise error

    monkeypatch.setattr(claude_gate.claude_client, "complete", _fail)
    with caplog.at_level("WARNING", logger="uvicorn.error"):
        assert claude_gate.claude_answer("s", "u") is None
    assert type(error).__name__ in caplog.text
