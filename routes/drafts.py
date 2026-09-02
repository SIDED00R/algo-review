import re

import db
from fastapi import APIRouter, HTTPException

from routes.models import DraftSaveRequest

router = APIRouter()

# 키 하나가 에디터 자리 하나다 — 메인 리뷰 탭은 `main`, 문제 뷰어는 `codeforces:{ref}`.
# 이 값이 그대로 PK 가 된다.
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,80}$")


def _require_key(draft_key: str) -> str:
    if not _KEY_PATTERN.match(draft_key):
        raise HTTPException(status_code=400, detail="임시 저장 키 형식이 올바르지 않습니다.")
    return draft_key


@router.get("/api/drafts/{draft_key}")
def get_draft(draft_key: str):
    key = _require_key(draft_key)
    draft = db.get_draft(key)
    # 없는 임시 저장본은 404 가 아니라 빈 값이다 — 프론트는 이것으로 '아직 없음' 과
    # '조회 실패' 를 구분한다.
    if draft is None:
        return {"key": key, "code": "", "language": "", "updated_at": None}
    return draft


@router.post("/api/drafts/{draft_key}")
def save_draft(draft_key: str, req: DraftSaveRequest):
    key = _require_key(draft_key)
    # 빈 코드는 삭제다 — updated_at 이 None 이면 저장본이 없다는 뜻이다.
    updated_at = db.save_draft(key, req.code, req.language)
    return {"key": key, "updated_at": updated_at}
