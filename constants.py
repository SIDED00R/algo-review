"""플랫폼·티어 상수 — 레이어 어디서나 참조하는 순수 값만 둔다.

DB 레이어와 외부 클라이언트는 레이어 다이어그램에서 형제다. 이 값들을 `clients` 에 두면
`import db` 만 해도 `requests`·`bs4` 가 함께 로드되는 역의존이 생긴다.

플랫폼 화이트리스트도 여기 하나뿐이다 — 여러 곳에 두면 새 플랫폼을 붙일 때 한 곳만
고쳐 조용히 어긋난다.
"""

PLATFORMS = ("codeforces", "boj")

TIER_NAMES = {
    0: "Unrated",
    1: "Bronze V", 2: "Bronze IV", 3: "Bronze III", 4: "Bronze II", 5: "Bronze I",
    6: "Silver V", 7: "Silver IV", 8: "Silver III", 9: "Silver II", 10: "Silver I",
    11: "Gold V", 12: "Gold IV", 13: "Gold III", 14: "Gold II", 15: "Gold I",
    16: "Platinum V", 17: "Platinum IV", 18: "Platinum III", 19: "Platinum II", 20: "Platinum I",
    21: "Diamond V", 22: "Diamond IV", 23: "Diamond III", 24: "Diamond II", 25: "Diamond I",
    26: "Ruby V", 27: "Ruby IV", 28: "Ruby III", 29: "Ruby II", 30: "Ruby I",
}


def normalize_platform(value: str, default: str = "boj") -> str:
    """소문자로 정규화한다. 화이트리스트 검증은 하지 않는다. 호출부마다 실패 방식이
    다르다(pydantic 은 ValueError, 라우터는 HTTPException 400)."""
    return (value or default).strip().lower()


def is_supported_platform(value: str) -> bool:
    return value in PLATFORMS
