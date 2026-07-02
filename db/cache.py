import json
from datetime import datetime, timezone
from db.connection import USE_POSTGRES, _ph, db_cursor

# 외부 API 파생 페이로드의 DB 캐시 — Cloud Run 콜드 스타트에도 살아남는다.
# TTL은 컬럼이 아니라 읽기 시점에 판정한다 (SQLite/Postgres 날짜 연산 방언 회피).


def _fetch(key: str):
    p = _ph()
    with db_cursor() as cur:
        cur.execute(f"SELECT payload, updated_at FROM api_cache WHERE cache_key = {p}", (key,))
        return cur.fetchone()


def cache_get(key: str, max_age_sec: int):
    """신선한 캐시 페이로드를 반환한다. 부재·만료 시 None."""
    row = _fetch(key)
    if not row:
        return None
    payload, updated_at = row[0], row[1]
    # 인스턴스 간 TZ 차이가 만료 판정을 흔들지 않게 UTC aware 로 통일한다.
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)).total_seconds()
    if age > max_age_sec:
        return None
    return json.loads(payload)


def cache_get_stale(key: str):
    """수명과 무관하게 캐시 페이로드를 반환한다 — 외부 API 실패 시 폴백용."""
    row = _fetch(key)
    return json.loads(row[0]) if row else None


def cache_set(key: str, payload) -> None:
    """JSON 직렬화 가능한 페이로드를 upsert한다."""
    p = _ph()
    data = json.dumps(payload, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    with db_cursor(commit=True) as cur:
        if USE_POSTGRES:
            cur.execute(f"""
                INSERT INTO api_cache (cache_key, payload, updated_at)
                VALUES ({p},{p},{p})
                ON CONFLICT (cache_key) DO UPDATE
                    SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
            """, (key, data, now))
        else:
            cur.execute(f"""
                INSERT OR REPLACE INTO api_cache (cache_key, payload, updated_at)
                VALUES ({p},{p},{p})
            """, (key, data, now))
