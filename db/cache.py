import json
from datetime import datetime, timezone

from db.connection import session_scope
from db.models import ApiCache

# 외부 API 파생 페이로드의 DB 캐시 — Cloud Run 콜드 스타트에도 살아남는다.
# TTL은 컬럼이 아니라 읽기 시점에 판정한다.


def _fetch(key: str):
    with session_scope() as session:
        obj = session.get(ApiCache, key)
        if obj is None:
            return None
        return obj.payload, obj.updated_at


def cache_get(key: str, max_age_sec: int):
    """신선한 캐시 페이로드를 반환한다. 부재·만료 시 None."""
    row = _fetch(key)
    if not row:
        return None
    payload, updated_at = row
    # 인스턴스 간 TZ 차이가 만료 판정을 흔들지 않게 UTC aware 로 통일한다.
    # 파싱 불가한 시각(naive 로 적힌 옛 행 등)은 만료로 취급한다 — 여기서 예외가 나가면
    # 호출부가 cache_set 에 도달하지 못해 그 키가 영구히 자가 복구 불능이 된다.
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)).total_seconds()
    except (TypeError, ValueError):
        return None
    if age > max_age_sec:
        return None
    return json.loads(payload)


def cache_get_stale(key: str):
    """수명과 무관하게 캐시 페이로드를 반환한다 — 외부 API 실패 시 폴백용."""
    row = _fetch(key)
    return json.loads(row[0]) if row else None


def cache_set(key: str, payload) -> None:
    """JSON 직렬화 가능한 페이로드를 upsert한다."""
    data = json.dumps(payload, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    with session_scope(commit=True) as session:
        session.merge(ApiCache(cache_key=key, payload=data, updated_at=now))
