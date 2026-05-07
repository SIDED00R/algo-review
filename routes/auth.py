import os
import secrets
import time
import logging
import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from routes.models import SetRepoRequest
from demo_mode import IS_DEMO, DEMO_GITHUB_STATUS, DEMO_REPOS

_logger = logging.getLogger(__name__)

router = APIRouter()

# CSRF state 토큰: {token: expires_at} — 5분 유효, 단일 서버 메모리 저장
_OAUTH_STATES: dict[str, float] = {}
_STATE_TTL = 300  # seconds


def _new_state() -> str:
    token = secrets.token_urlsafe(32)
    _OAUTH_STATES[token] = time.time() + _STATE_TTL
    return token


def _consume_state(token: str) -> bool:
    """검증 후 즉시 삭제. 만료된 항목도 정리."""
    now = time.time()
    expired = [k for k, exp in _OAUTH_STATES.items() if exp < now]
    for k in expired:
        del _OAUTH_STATES[k]
    return bool(_OAUTH_STATES.pop(token, None))


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
    callback_url = f"{app_url}/auth/github/callback"
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope=repo&redirect_uri={callback_url}&state={state}"
    )
    return RedirectResponse(github_url)


@router.get("/auth/github/callback")
def github_oauth_callback(code: str = "", error: str = "", state: str = ""):
    client_id, client_secret, app_url = _github_oauth_settings()
    if error or not code:
        return RedirectResponse(f"{app_url}/?github=error")
    if not _consume_state(state):
        _logger.warning("GitHub OAuth callback: invalid or expired state token")
        return RedirectResponse(f"{app_url}/?github=error")
    try:
        token = api_client.exchange_github_code(code, client_id, client_secret)
        user = api_client.get_github_user(token)
        username = user.get("login", "")
        db.save_github_settings(access_token=token, github_username=username)
    except Exception:
        _logger.exception("GitHub OAuth callback failed")
        return RedirectResponse(f"{app_url}/?github=error")
    return RedirectResponse(f"{app_url}/?github=connected&user={username}")


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
