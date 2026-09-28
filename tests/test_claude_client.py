"""Claude 구독 원샷 호출 — SDK 가 돌려준 메시지를 답 또는 ClaudeUnavailable 로 가른다(CLI 를 띄우지 않는다)."""
import threading

import anyio
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

import claude_client
from claude_client import ClaudeUnavailable


def _result(text="답", *, is_error=False, stop_reason="end_turn", status=None):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=1, session_id="s", stop_reason=stop_reason, result=text,
                         api_error_status=status)


def _fake_query(messages, calls=None, delay=0.0):
    async def _query(*, prompt, options):
        if calls is not None:
            calls.append((prompt, options))
        if delay:
            await anyio.sleep(delay)
        for message in messages:
            yield message
    return _query


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(claude_client.settings, "claude_code_oauth_token", "tok")
    monkeypatch.setattr(claude_client.settings, "claude_model", None)
    monkeypatch.setattr(claude_client, "_slots", threading.BoundedSemaphore(claude_client._MAX_CONCURRENT))


def test_returns_the_result_text(monkeypatch):
    monkeypatch.setattr(claude_client, "query", _fake_query([_result("  답변  ")]))
    assert claude_client.complete("sys", "user") == "답변"


def test_options_give_the_cli_no_tools_settings_or_mcp(monkeypatch):
    """도구가 하나라도 남으면 프롬프트에 실린 외부 문제 본문이 컨테이너에서 명령을 실행시킬 수 있다."""
    calls = []
    monkeypatch.setattr(claude_client, "query", _fake_query([_result()], calls))
    claude_client.complete("시스템", "질문")

    prompt, options = calls[0]
    assert prompt == "질문"
    assert options.system_prompt == "시스템"
    assert options.tools == []
    assert options.verbatim_prompts is True   # 없으면 본문 속 `@<경로>` 가 파일 내용으로 펼쳐진다
    assert options.setting_sources == []
    assert options.strict_mcp_config is True
    assert options.max_turns == 1
    assert options.env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"


def test_sdk_turns_the_options_into_an_empty_tool_list_flag():
    """SDK 가 `tools=[]` 를 CLI 인자로 옮기는 방식이 바뀌면(예: 빈 목록을 생략) 도구가 기본값으로 돌아온다."""
    transport = SubprocessCLITransport(prompt="x", options=claude_client._options("s"))
    transport._cli_path = "claude"
    cmd = transport._build_command()
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--setting-sources=" in cmd
    assert "--strict-mcp-config" in cmd
    assert "--no-session-persistence" in cmd


@pytest.mark.parametrize("messages, reason", [
    ([AssistantMessage(content=[], model="m", error="rate_limit"), _result()], "rate_limit"),
    ([_result(is_error=True, status=429)], "status=429"),
    ([_result(stop_reason="max_tokens")], "잘림"),
    ([_result("   ")], "빈 답"),
    ([], "결과 메시지 없음"),
])
def test_unusable_answers_raise_claude_unavailable(monkeypatch, messages, reason):
    monkeypatch.setattr(claude_client, "query", _fake_query(messages))
    with pytest.raises(ClaudeUnavailable, match=reason):
        claude_client.complete("sys", "user")


def test_missing_token_raises_without_starting_the_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(claude_client.settings, "claude_code_oauth_token", "")
    monkeypatch.setattr(claude_client, "query", _fake_query([_result()], calls))
    with pytest.raises(ClaudeUnavailable, match="미설정"):
        claude_client.complete("sys", "user")
    assert calls == []


def test_slow_answer_times_out(monkeypatch):
    monkeypatch.setattr(claude_client, "_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(claude_client, "query", _fake_query([_result()], delay=1))
    with pytest.raises(ClaudeUnavailable, match="초 안에 답이 없음"):
        claude_client.complete("sys", "user")


def test_full_slots_give_up_after_the_wait(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(claude_client, "_slots", slots)
    monkeypatch.setattr(claude_client, "_SLOT_WAIT_SEC", 0.01)
    monkeypatch.setattr(claude_client, "query", _fake_query([_result()]))
    with pytest.raises(ClaudeUnavailable, match="동시 호출"):
        claude_client.complete("sys", "user")


def test_failed_call_returns_its_slot(monkeypatch):
    monkeypatch.setattr(claude_client, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(claude_client, "_SLOT_WAIT_SEC", 0.01)
    monkeypatch.setattr(claude_client, "query", _fake_query([_result(is_error=True)]))
    with pytest.raises(ClaudeUnavailable):
        claude_client.complete("sys", "user")

    monkeypatch.setattr(claude_client, "query", _fake_query([_result("다음 답")]))
    assert claude_client.complete("sys", "user") == "다음 답"
