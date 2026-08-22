"""저장되는 시각의 단일 규약 — 항상 UTC, 항상 오프셋을 붙인다.

오프셋 없이 저장하면 그 문자열이 **어느 지역의 벽시계인지 알 수 없다**. Cloud Run 컨테이너는
UTC(Dockerfile 에 TZ 를 두지 않는다)이고 개발 기계는 KST 라, 같은 코드가 만든 값의 의미가
환경마다 달랐다. 그래서 같은 제출이 GitHub README(KST 로 변환해 표기)와 앱 화면(원문을
그대로 잘라 표기)에서 **다른 날짜**로 보였다 — 한국 시각 00:00~09:00 제출은 앱에서 전날로
찍혔다(하루의 9시간).

읽는 쪽은 `parse_stored` 를 쓴다. 오프셋이 없는 옛 행은 UTC 로 본다 — 운영 DB 에 쓴 것이
Cloud Run(UTC)뿐이기 때문이다. 프론트의 `utils.js: parseStoredTime` 이 같은 규칙을 쓴다.
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
