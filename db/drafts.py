"""code_drafts 테이블 CRUD — 에디터 임시 저장본.

키 하나가 에디터 자리 하나다(메인 리뷰 탭 `main`, 문제 뷰어 `codeforces:{ref}`).
빈 코드는 저장하지 않고 행을 지운다.
"""
from sqlalchemy.exc import IntegrityError

from db.connection import session_scope
from db.models import CodeDraft
from timestamps import utc_now_iso


def get_draft(draft_key: str) -> dict | None:
    with session_scope() as session:
        obj = session.get(CodeDraft, draft_key)
        if obj is None:
            return None
        return {
            "key": obj.draft_key,
            "code": obj.code,
            "language": obj.language,
            "updated_at": obj.updated_at,
        }


def _merge_draft(draft_key: str, code: str, language: str, now: str) -> None:
    with session_scope(commit=True) as session:
        session.merge(CodeDraft(draft_key=draft_key, code=code,
                                language=language, updated_at=now))


def save_draft(draft_key: str, code: str, language: str = "") -> str | None:
    """임시 저장본을 upsert 하고 저장 시각을 돌려준다. 코드가 비면 지우고 None 을 돌려준다."""
    if not code.strip():
        delete_draft(draft_key)
        return None
    now = utc_now_iso()
    try:
        _merge_draft(draft_key, code, language, now)
    except IntegrityError:
        # merge 는 SELECT 후 없으면 INSERT 다. 재시도 시점에는 행이 있어 UPDATE 가 된다.
        _merge_draft(draft_key, code, language, now)
    return now


def delete_draft(draft_key: str) -> None:
    with session_scope(commit=True) as session:
        obj = session.get(CodeDraft, draft_key)
        if obj is not None:
            session.delete(obj)
