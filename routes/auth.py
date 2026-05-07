import os
import hmac
import hashlib
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

_STATE_TTL = 300  # seconds
# GITHUB_CLIENT_SECRET을 HMAC 서명 키로 재사용 — 별도 환경변수 없이 안전
_HMAC_KEY = os.environ.get("GITHUB_CLIENT_SECRET", "").encode() or b"dev-fallback-key"


def _new_state() -> str:
    """현재 타임스탬프를 HMAC-SHA256으로 서명 — stateless, 인스턴스·재시작 무관."""
    ts = str(int(time.time()))
    sig = hmac.new(_HMAC_KEY, ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def _verify_state(state: str) -> bool:
    """서명 검증 + TTL 확인. 타이밍 공격 방지를 위해 compare_digest 사용."""
    try:
        ts_str, sig = state.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_HMAC_KEY, ts_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    return (time.time() - int(ts_str)) < _STATE_TTL


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
    if not _verify_state(state):
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
