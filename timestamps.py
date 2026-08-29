"""저장되는 시각의 단일 규약 — 항상 UTC, 항상 오프셋을 붙인다.

Cloud Run 컨테이너는 UTC(Dockerfile 에 TZ 를 두지 않는다)이고 개발 기계는 KST 다.

읽는 쪽은 `parse_stored` 를 쓴다. 오프셋이 없는 옛 행은 UTC 로 본다 — 운영 DB 에 쓴 것이
Cloud Run(UTC)뿐이다. 프론트의 `utils.js: parseStoredTime` 이 같은 규칙을 쓴다.
"""
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """저장용 현재 시각.

    ISO-8601 이라 사전순 = 시간순이 유지된다 — created_at·imported_at 은 SQL 정렬 키다.
    """
    return datetime.now(timezone.utc).isoformat()


def parse_stored(value: str) -> datetime:
    """저장된 시각 문자열을 aware datetime 으로. 오프셋이 없으면 UTC 로 본다."""
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
