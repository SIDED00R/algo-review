import os
import hmac
import hashlib
import secrets
import time
import logging
import db
import clients as api_client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from routes.models import SetRepoRequest
from demo_mode import IS_DEMO, DEMO_GITHUB_STATUS, DEMO_REPOS

_logger = logging.getLogger(__name__)

router = APIRouter()

_STATE_TTL = 300  # seconds
_HMAC_KEY = os.environ.get("GITHUB_CLIENT_SECRET", "").encode() or b"dev-fallback-key"
# 사용된 nonce → 만료 시각. TTL 만료된 것만 정리해 1000개 일괄 삭제로 인한 replay 창 재개를 방지.
_USED_NONCES: dict[str, float] = {}


def _new_state() -> str:
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    sig = hmac.new(_HMAC_KEY, f"{nonce}.{ts}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{ts}.{sig}"


def _validate_state(state: str) -> tuple[bool, str]:
    """nonce를 반환하되 소비하지 않음."""
    try:
        nonce, ts_str, sig = state.split(".", 2)
    except ValueError:
        return False, ""
    expected = hmac.new(_HMAC_KEY, f"{nonce}.{ts_str}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False, ""
    if (time.time() - int(ts_str)) >= _STATE_TTL:
        return False, ""
    if nonce in _USED_NONCES and _USED_NONCES[nonce] > time.time():
        return False, ""
    return True, nonce


def _consume_nonce(nonce: str) -> None:
    """트랜잭션 성공 후에만 호출. 만료된 항목만 정리해 유효 기간 내 nonce는 항상 차단."""
    now = time.time()
    _USED_NONCES[nonce] = now + _STATE_TTL
    # 만료된 항목만 제거 — 일괄 삭제 금지 (삭제 직후 기존 nonce replay 가능해짐)
    expired = [k for k, exp in _USED_NONCES.items() if exp <= now]
    for k in expired:
        del _USED_NONCES[k]


def _github_oauth_settings():
    client_id = os.environ.get("GITHUB_CLIENT_ID", "")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
    app_url = os.environ.get("APP_URL", "http://localhost:8080")
    return client_id, client_secret, app_url


@router.get("/auth/github")
def github_oauth_start():
    if IS_DEMO:
        app_url = os.environ.get("APP_URL", "http://localhost:8080")
        return RedirectResponse(f"{app_url}/?github=connected&user=demo_user")
    client_id, _, app_url = _github_oauth_settings()
    if not client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID가 설정되지 않았습니다.")
    state = _new_state()
    nonce = state.split(".")[0]
    callback_url = f"{app_url}/auth/github/callback"
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope=repo&redirect_uri={callback_url}&state={state}"
    )
    redirect = RedirectResponse(github_url)
    # nonce를 HttpOnly 쿠키로 브라우저에 바인딩 — 다른 브라우저의 콜백 재사용 차단
    redirect.set_cookie(
        key="oauth_nonce",
        value=nonce,
        httponly=True,
        samesite="lax",
        secure=app_url.startswith("https://"),
        max_age=_STATE_TTL,
        path="/",
    )
    return redirect


@router.get("/auth/github/callback")
def github_oauth_callback(request: Request, code: str = "", error: str = "", state: str = ""):
    client_id, client_secret, app_url = _github_oauth_settings()
    if error or not code:
        return RedirectResponse(f"{app_url}/?github=error")
    # 쿠키 nonce와 state nonce가 일치해야 콜백이 같은 브라우저에서 시작됐음을 보장
    cookie_nonce = request.cookies.get("oauth_nonce", "")
    state_nonce = state.split(".")[0] if state else ""
    if not cookie_nonce or not hmac.compare_digest(cookie_nonce, state_nonce):
        _logger.warning("GitHub OAuth callback: nonce mismatch (possible CSRF)")
        return RedirectResponse(f"{app_url}/?github=error")
    valid, nonce = _validate_state(state)
    if not valid:
        _logger.warning("GitHub OAuth callback: invalid or expired state token")
        return RedirectResponse(f"{app_url}/?github=error")
    try:
        token = api_client.exchange_github_code(code, client_id, client_secret)
        user = api_client.get_github_user(token)
        username = user.get("login", "")
        db.save_github_settings(access_token=token, github_username=username)
    except Exception:
        _logger.exception("GitHub OAuth callback failed")
        # nonce를 소비하지 않아 재시도 가능
        return RedirectResponse(f"{app_url}/?github=error")
    # 트랜잭션 성공 후 nonce 소비 — 이후 같은 state로 재진입 불가
    _consume_nonce(nonce)
    redirect = RedirectResponse(f"{app_url}/?github=connected&user={username}")
    redirect.delete_cookie("oauth_nonce", path="/")
    return redirect


@router.get("/auth/github/status")
def github_status():
    if IS_DEMO:
        return DEMO_GITHUB_STATUS
    settings = db.get_github_settings()
    if not settings:
        return {"connected": False}
    return {
        "connected": True,
        "username": settings.get("github_username", ""),
        "target_repo": settings.get("target_repo", ""),
    }


@router.post("/auth/github/repo")
def set_github_repo(req: SetRepoRequest):
    if not db.get_github_settings():
        raise HTTPException(status_code=400, detail="GitHub 연결 먼저 해주세요.")
    repo = req.repo.strip()
    if not repo or "/" not in repo:
        raise HTTPException(status_code=400, detail="저장소를 owner/repo 형식으로 입력하세요.")
    db.update_github_target_repo(repo)
    return {"ok": True, "target_repo": repo}


@router.delete("/auth/github")
def github_disconnect():
    db.delete_github_settings()
    return {"ok": True}


@router.get("/auth/github/repos")
def get_github_repos():
    if IS_DEMO:
        return {"repos": DEMO_REPOS}
    settings = db.get_github_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="GitHub 연결이 필요합니다.")
    try:
        repos = api_client.get_github_user_repos(settings["access_token"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"레포지토리 조회 실패: {e}")
    return {"repos": repos}
