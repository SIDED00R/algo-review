from clients import search_cf_problems_by_tag, TIER_NAMES

# 테마별 문제 둘러보기 (Codeforces) — 사용자 데이터와 무관하게 알고리즘 분야별 대표 문제를 제공한다.
# tag 는 Codeforces problemset 태그명(공백 포함, 대소문자 그대로).
THEMES = [
    {"label": "다이나믹 프로그래밍", "tag": "dp"},
    {"label": "그리디 알고리즘",     "tag": "greedy"},
    {"label": "그래프 이론",         "tag": "graphs"},
    {"label": "완전 탐색",           "tag": "brute force"},
    {"label": "DFS / 탐색",          "tag": "dfs and similar"},
    {"label": "이분 탐색",           "tag": "binary search"},
    {"label": "최단 경로",           "tag": "shortest paths"},
    {"label": "자료 구조",           "tag": "data structures"},
    {"label": "문자열",              "tag": "strings"},
    {"label": "수학",                "tag": "math"},
]

PROBLEMS_PER_THEME = 3

# CF 레이팅(800~3500) → 백준식 티어(1~30) 임의 매핑.
# 100점당 1티어, rating 800 = Bronze II(4) 기준의 선형 매핑.
CF_RATING_MIN = 800
CF_RATING_MAX = 3500
_TIER_STEP = 100
_TIER_BASE = 4  # rating 800 → tier 4 (Bronze II)

# 난이도 밴드(점수 기준) — 각 밴드에서 1문제씩 뽑아 쉬움→어려움 사다리를 구성한다.
_DIFFICULTY_BANDS = [
    (CF_RATING_MIN, 1199),   # 입문
    (1200, 1699),            # 중급
    (1700, CF_RATING_MAX),   # 고급
]


def cf_rating_to_tier(rating: int | None) -> int:
    """CF 레이팅을 백준식 티어(1~30)로 매핑한다. rating 없으면 0(Unrated)."""
    if not rating:
        return 0
    tier = round((rating - CF_RATING_MIN) / _TIER_STEP) + _TIER_BASE
    return max(1, min(30, tier))


def _pick_difficulty_ladder(pool: list[dict], n: int = PROBLEMS_PER_THEME) -> list[dict]:
    """레이팅 밴드별로 가장 많이 풀린 문제를 1개씩 뽑아 난이도 사다리를 만든다.
    pool 은 solved_count 내림차순으로 정렬되어 있다고 가정한다."""
    seen: set = set()
    picked: list[dict] = []

    for lo, hi in _DIFFICULTY_BANDS:
        for p in pool:
            rating = p.get("rating") or 0
            if p["id"] not in seen and lo <= rating <= hi:
                picked.append(p)
                seen.add(p["id"])
                break

    # 빈 밴드로 n개에 못 미치면 남은 인기 문제로 채운다.
    if len(picked) < n:
        for p in pool:
            if p["id"] not in seen:
                picked.append(p)
                seen.add(p["id"])
                if len(picked) >= n:
                    break

    picked.sort(key=lambda p: p.get("rating") or 0)
    return picked[:n]


def get_theme_problems() -> list[dict]:
    """각 테마 태그에서 난이도 밴드별 대표 문제를 뽑고, CF 레이팅을 티어로 매핑해 반환한다."""
    results = []
    for theme in THEMES:
        pool = search_cf_problems_by_tag(
            theme["tag"], CF_RATING_MIN, CF_RATING_MAX, exclude_refs=set(),
        )
        problems = _pick_difficulty_ladder(pool)
        for p in problems:
            tier = cf_rating_to_tier(p.get("rating"))
            p["tier"] = tier
            p["tier_name"] = TIER_NAMES.get(tier, "Unrated")
            # 프론트가 쓰지 않는 필드 제거 — 문제는 data-ref로 인앱 뷰어를 연다.
            p.pop("rating", None)
            p.pop("url", None)
        results.append({
            "label": theme["label"],
            "tag": theme["tag"],
            "problems": problems,
        })
    return results
