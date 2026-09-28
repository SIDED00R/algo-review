"""Claude 구독 원샷 호출 — Claude Agent SDK 가 띄운 CLI 에 한 번 묻고 답 한 덩어리를 받는다.

도구는 하나도 주지 않고 프롬프트는 글자 그대로 보낸다. 프롬프트에는 외부 문제 본문과 사용자
코드가 실리므로, 도구가 있으면 그 안의 지시문이 컨테이너에서 명령을 실행하거나 파일을 읽게 만들
수 있다. 도구가 없어도 CLI 는 기본값으로 프롬프트 속 `@<경로>` 를 추론 전에 파일 내용으로
펼친다 — `verbatim_prompts` 가 이것과 슬래시 명령 해석을 끈다.
"""
import threading
from contextlib import aclosing

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

from config import settings

# 호출마다 CLI 프로세스가 하나 뜬다(상주 메모리 약 230MB, 로컬 실측). 동시 호출을 묶지
# 않으면 번역 4섹션 동시 요청만으로 인스턴스 메모리(1GiB)를 넘긴다.
_MAX_CONCURRENT = 2
_SLOT_WAIT_SEC = 30
_TIMEOUT_SEC = 120
_slots = threading.BoundedSemaphore(_MAX_CONCURRENT)

# 자동 업데이트·원격 측정처럼 답과 무관한 네트워크 호출을 끈다.
_CLI_ENV = {"DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}


class ClaudeUnavailable(Exception):
    """Claude 에게서 쓸 수 있는 답을 받지 못했다. 메시지는 로그용 사유다."""


def is_configured() -> bool:
    return bool(settings.claude_code_oauth_token)


def complete(system_prompt: str, user_prompt: str) -> str:
    """답 본문을 돌려준다. 쓸 수 있는 답이 없으면 ClaudeUnavailable 을 던진다.

    동기 함수다 — 라우터의 스레드풀 워커에서 부르므로 호출마다 이벤트 루프를 따로 돌린다.
    """
    if not is_configured():
        raise ClaudeUnavailable("CLAUDE_CODE_OAUTH_TOKEN 미설정")
    if not _slots.acquire(timeout=_SLOT_WAIT_SEC):
        raise ClaudeUnavailable(f"동시 호출 {_MAX_CONCURRENT}개가 {_SLOT_WAIT_SEC}초 넘게 차 있음")
    try:
        return anyio.run(_ask, system_prompt, user_prompt)
    except TimeoutError as e:
        raise ClaudeUnavailable(f"{_TIMEOUT_SEC}초 안에 답이 없음") from e
    finally:
        _slots.release()


def _options(system_prompt: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        tools=[],                # CLI 에 --tools "" 로 전달된다 — 내장 도구를 전부 뺀다
        verbatim_prompts=True,   # `@<경로>` 파일 펼치기·슬래시 명령을 끈다(CLI 2.1.248 이상)
        setting_sources=[],      # 사용자·프로젝트 설정 파일(훅·권한·CLAUDE.md)을 읽지 않는다
        strict_mcp_config=True,  # MCP 서버를 하나도 붙이지 않는다
        max_turns=1,
        model=settings.claude_model or None,
        # 세션 기록을 디스크에 남기지 않는다 — Cloud Run 의 파일시스템은 메모리를 쓴다.
        extra_args={"no-session-persistence": None},
        env={**_CLI_ENV, "CLAUDE_CODE_OAUTH_TOKEN": settings.claude_code_oauth_token},
    )


async def _ask(system_prompt: str, user_prompt: str) -> str:
    error = None
    result = None
    with anyio.fail_after(_TIMEOUT_SEC):
        async with aclosing(query(prompt=user_prompt, options=_options(system_prompt))) as messages:
            async for message in messages:
                if isinstance(message, AssistantMessage) and message.error:
                    error = message.error
                elif isinstance(message, ResultMessage):
                    result = message
    if error:
        raise ClaudeUnavailable(f"assistant error: {error}")
    if result is None:
        raise ClaudeUnavailable("결과 메시지 없음")
    if result.is_error:
        raise ClaudeUnavailable(
            f"result error: subtype={result.subtype} status={result.api_error_status}")
    if result.stop_reason == "max_tokens":
        raise ClaudeUnavailable("출력 상한에 걸려 답이 잘림")
    text = (result.result or "").strip()
    if not text:
        raise ClaudeUnavailable("빈 답")
    return text
