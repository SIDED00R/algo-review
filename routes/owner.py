"""소유자 열쇠 등록 — 맞는 열쇠를 보내면 HttpOnly 쿠키로 심는다. 판정은 owner_access 가 요청마다 한다."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from config import settings
from demo_mode import IS_DEMO, demo_block
from owner_access import COOKIE_NAME, key_matches
from routes.models import OwnerKeyRequest

router = APIRouter()

_COOKIE_MAX_AGE = 365 * 24 * 3600


@router.post("/api/owner/key")
def register_owner_key(req: OwnerKeyRequest):
    if IS_DEMO:
        demo_block("소유자 열쇠 등록은 데모 버전에서 지원되지 않습니다.")
    if not key_matches(req.key):
        raise HTTPException(status_code=403, detail="열쇠가 맞지 않습니다.")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=req.key,
        max_age=_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        secure=settings.app_url.startswith("https://"),
        samesite="strict",
    )
    return response
