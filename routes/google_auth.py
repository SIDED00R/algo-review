"""구글 로그인 흐름 — 구글로 보내고, 돌아온 인가 코드로 이메일을 확인해 세션 쿠키를 심는다.

세션 검증과 미로그인 요청 차단은 login_gate 가 요청마다 한다. 데모는 로그인이 없어 첫 화면으로 보낸다.
"""
import hmac
import logging
import secrets
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import clients as api_client
from config import settings
from demo_mode import IS_DEMO
from login_gate import SESSION_COOKIE, SESSION_TTL, allowed_emails, make_session, missing_login_settings

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

_STATE_COOKIE = "google_oauth_state"
_STATE_TTL = 600
_STATE_PATH = "/auth/google"


def _secure() -> bool:
    return settings.app_url.startswith("https://")


def _redirect_uri() -> str:
    return f"{settings.app_url}/auth/google/callback"


def _login_failed(message: str, status_code: int) -> HTMLResponse:
    return HTMLResponse(status_code=status_code, content=(
        '<!doctype html><meta charset="utf-8"><title>로그인 실패</title>'
        f"<p>{escape(message)}</p><p><a href=\"/auth/google\">다시 로그인</a></p>"))


def _missing_settings_page() -> HTMLResponse | None:
    """로그인에 필요한 설정이 빠졌으면 503 안내. 게이트와 같은 기준(login_gate.missing_login_settings)이다."""
    missing = missing_login_settings()
    if not missing:
        return None
    return _login_failed(f"로그인 설정({'·'.join(missing)})이 없습니다. 서버 설정을 확인해주세요.", 503)


@router.get("/auth/google")
def google_login_start():
    if IS_DEMO:
        return RedirectResponse("/")
    if (page := _missing_settings_page()) is not None:
        return page
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(api_client.google_auth_url(settings.google_client_id, _redirect_uri(), state))
    # 콜백은 구글에서 넘어오는 최상위 이동이라 SameSite=Lax 여야 이 쿠키가 실린다.
    response.set_cookie(_STATE_COOKIE, state, max_age=_STATE_TTL, path=_STATE_PATH,
                        httponly=True, samesite="lax", secure=_secure())
    return response


@router.get("/auth/google/callback")
def google_login_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if IS_DEMO:
        return RedirectResponse("/")
    if (page := _missing_settings_page()) is not None:
        return page
    expected = request.cookies.get(_STATE_COOKIE, "")
    # compare_digest 는 non-ASCII str 에 TypeError 를 던진다 — state 쿼리와 state 쿠키 모두 요청자가
    # 정하는 임의 문자열이다(쿠키는 `"\351"` 같은 8진 이스케이프로도 비ASCII 가 된다).
    if (error or not code or not expected or not state.isascii() or not expected.isascii()
            or not hmac.compare_digest(expected, state)):
        return _login_failed("로그인이 완료되지 않았습니다. 다시 시도해주세요.", 400)
    try:
        claims = api_client.exchange_google_code(
            code, settings.google_client_id, settings.google_client_secret, _redirect_uri())
    except Exception as e:
        logger.warning("구글 로그인 토큰 교환 실패: %s", type(e).__name__)
        return _login_failed("구글에서 로그인 정보를 받지 못했습니다. 다시 시도해주세요.", 502)
    email = str(claims.get("email") or "").lower()
    if claims.get("email_verified") is not True or email not in allowed_emails():
        logger.warning("허용되지 않은 계정의 로그인 시도")
        return _login_failed("이 구글 계정은 허용되지 않았습니다.", 403)
    response = RedirectResponse("/")
    # Lax — Strict 면 구글에서 넘어온 이동 직후의 / 요청에 쿠키가 실리지 않아 다시 로그인으로 돈다.
    response.set_cookie(SESSION_COOKIE, make_session(email), max_age=SESSION_TTL, path="/",
                        httponly=True, samesite="lax", secure=_secure())
    response.delete_cookie(_STATE_COOKIE, path=_STATE_PATH)
    return response
