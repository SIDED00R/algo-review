"""목록 API 의 페이지네이션·검색 공통 규약.

리뷰 기록과 가져온 기록이 같은 규약을 쓴다 — 두 벌로 만들면 같은 검색어가 탭마다 다른
결과를 주고, 한쪽에만 상한이 빠진다.
"""
from sqlalchemy import func, or_


# 목록 페이지 크기 상한. 프론트가 per_page 를 보내지만 서버가 마지막 말을 한다 —
# 상한이 없으면 `?per_page=999999` 하나로 전 행 응답이 되살아난다.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def paging_bounds(page, per_page) -> tuple[int, int]:
    """(page, per_page) 를 안전한 범위로 자른다."""
    page = max(1, int(page or 1))
    per_page = min(MAX_PAGE_SIZE, max(1, int(per_page or DEFAULT_PAGE_SIZE)))
    return page, per_page


def search_filter(columns, q: str):
    """제목·문제번호·태그를 한 덩어리로 보는 검색 술어.

    검색 판정은 여기 한 곳에만 둔다 — 프론트가 받은 목록을 다시 거르면 같은 검색어가
    화면과 서버에서 다른 결과를 준다. 대소문자 무시는 `lower()` 로 방언 차이를 없앤다
    (Postgres 의 ILIKE 는 SQLite 에 없다).
    """
    raw = (q or "").strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needle = f"%{raw}%"
    return or_(*[func.lower(col).like(needle, escape="\\") for col in columns])
