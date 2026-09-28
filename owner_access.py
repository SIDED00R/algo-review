"""소유자 판정 — 요청이 소유자 열쇠 쿠키를 가졌는지 요청 범위 contextvar 로 전한다.

Claude 구독은 소유자 본인의 요청에만 쓴다. 운영 서비스는 인증 없이 공개돼 있어 URL 만
알면 누구나 부를 수 있다.

미들웨어가 요청마다 판정해 contextvar 에 넣는다. 스레드풀(동기 라우터)·`asyncio.to_thread`
는 contextvar 를 복사해 가므로 LLM 을 부르는 워커 스레드에서도 같은 값이 보인다.
"""
import contextvars
import hmac

from starlette.requests import HTTPConnection

from config import settings

COOKIE_NAME = "owner_key"

_is_owner = contextvars.ContextVar("is_owner", default=False)


def key_matches(candidate: str) -> bool:
    """설정된 열쇠와 같은지. 열쇠가 설정되지 않았으면 항상 False 다.

    compare_digest 는 non-ASCII str 에 TypeError 를 던진다 — 쿠키·요청 본문은 임의
    문자열이라 먼저 걸러낸다.
    """
    expected = settings.owner_key
    if not expected or not candidate or not candidate.isascii():
        return False
    return hmac.compare_digest(candidate, expected)


def is_owner_request() -> bool:
    return _is_owner.get()


class OwnerContextMiddleware:
    """요청의 `owner_key` 쿠키를 판정해 그 요청을 처리하는 동안 contextvar 에 둔다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _is_owner.set(key_matches(HTTPConnection(scope).cookies.get(COOKIE_NAME, "")))
        try:
            await self.app(scope, receive, send)
        finally:
            _is_owner.reset(token)
