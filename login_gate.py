"""로그인 게이트 — 운영 앱은 허용한 구글 계정으로 로그인한 요청만 받는다. 데모는 로그인 없이 쓴다.

세션은 서명한 쿠키 하나(`base64url(이메일, 패딩 없음).만료시각.서명`)다. 서버에 저장하지 않으므로 인스턴스가
여럿이어도 통한다. 서명 키는 GOOGLE_CLIENT_SECRET 에서 파생한다 — 그 비밀을 바꾸면 모든 세션이
끊긴다. 허용 이메일은 검증할 때마다 다시 본다 — 목록에서 빼면 기존 세션도 바로 막힌다.

로그인 없이 통과하는 경로: /health(배포 스모크), /api/execute(배포 워크플로가 무인증으로 예제
실행을 확인한다), 로그인 흐름(/auth/google, /auth/google/callback), 정적 자산(/static/).

Cloud Run(K_SERVICE) 위에서는 로그인에 필요한 설정이 빠지거나 APP_URL 이 https 주소가 아니면
열리는 대신 503 으로 막는다(APP_URL 은 콜백 주소와 쿠키 Secure 판정의 기준).
"""
import base64
import binascii
import hashlib
import hmac
import os
import time

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, RedirectResponse

from config import settings
from demo_mode import IS_DEMO

SESSION_COOKIE = "session"
SESSION_TTL = 30 * 24 * 3600

_PUBLIC_PATHS = ("/health", "/api/execute", "/auth/google", "/auth/google/callback")
_PUBLIC_PREFIXES = ("/static/",)


def allowed_emails() -> set[str]:
    return {e.strip().lower() for e in settings.auth_allowed_emails.split(",") if e.strip()}


def login_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret and allowed_emails())


def missing_login_settings() -> list[str]:
    """로그인을 돌리는 데 빠진 설정 이름. 비어 있으면 로그인할 수 있다."""
    missing = [name for name, value in (("GOOGLE_CLIENT_ID", settings.google_client_id),
                                        ("GOOGLE_CLIENT_SECRET", settings.google_client_secret))
               if not value]
    if not allowed_emails():
        missing.append("AUTH_ALLOWED_EMAILS")
    # 기본값(http://localhost:8080)이 남으면 구글이 콜백을 localhost 로 보내 아무도 로그인하지 못한다.
    if os.getenv("K_SERVICE") and not settings.app_url.startswith("https://"):
        missing.append("APP_URL(https 주소)")
    return missing


def login_required() -> bool:
    """데모가 아니고, 로그인이 설정됐거나 Cloud Run(K_SERVICE) 위라면 로그인을 요구한다.

    Cloud Run 에서 설정이 빠지면 앱이 열리는 대신 막힌다. 로컬·테스트는 설정이 없으면 열려 있다.
    """
    return not IS_DEMO and (login_configured() or bool(os.getenv("K_SERVICE")))


def _signature(payload: str) -> str:
    key = hmac.new(settings.google_client_secret.encode(), b"session-cookie", hashlib.sha256).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def make_session(email: str) -> str:
    # 패딩(=)을 뺀다 — `=` 가 든 값은 Set-Cookie 에서 따옴표로 감싸진다.
    encoded = base64.urlsafe_b64encode(email.lower().encode()).decode().rstrip("=")
    payload = f"{encoded}.{int(time.time()) + SESSION_TTL}"
    return f"{payload}.{_signature(payload)}"


def session_email(value: str) -> str | None:
    """서명·만료·허용 목록을 모두 통과한 세션의 이메일. 아니면 None."""
    parts = value.split(".")
    if len(parts) != 3 or not value.isascii():
        return None
    encoded, expires, signature = parts
    # compare_digest 는 non-ASCII str 에 TypeError 를 던진다 — 위에서 걸렀다.
    if not hmac.compare_digest(signature, _signature(f"{encoded}.{expires}")):
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    try:
        email = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    return email if email in allowed_emails() else None


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


class LoginGateMiddleware:
    """로그인하지 않은 요청을 앱에 닿기 전에 돌려보낸다. 셸 문서(/)는 로그인 화면으로 보낸다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not login_required() or _is_public(scope["path"]):
            await self.app(scope, receive, send)
            return
        missing = missing_login_settings()
        if missing:
            response = JSONResponse(status_code=503, content={
                "detail": f"로그인 설정({'·'.join(missing)})이 없어 막았습니다."})
        elif session_email(HTTPConnection(scope).cookies.get(SESSION_COOKIE, "")):
            await self.app(scope, receive, send)
            return
        elif scope["path"] == "/":
            # APP_URL 주소로 보낸다 — Cloud Run 주소가 둘이라 다른 주소에서 시작하면 state 쿠키가
            # 그 호스트에 심기고, APP_URL 로 오는 콜백에는 실리지 않는다.
            response = RedirectResponse(f"{settings.app_url}/auth/google")
        else:
            response = JSONResponse(status_code=401, content={
                "detail": "로그인이 필요합니다. 페이지를 새로고침해 다시 로그인해주세요."})
        await response(scope, receive, send)
