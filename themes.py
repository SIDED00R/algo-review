import db
from clients import search_cf_problems_by_tag, search_problems_by_tag

# 테마별 문제 둘러보기 — 알고리즘 분야별 대표 문제를 플랫폼(Codeforces/백준)별 네이티브 난이도로 제공한다.
# cf_tag 는 Codeforces problemset 태그명(공백 포함), boj_tag 는 solved.ac 태그 키.
THEMES = [
    {"id": "dp",              "label": "다이나믹 프로그래밍", "cf_tag": "dp",              "boj_tag": "dp"},
    {"id": "greedy",          "label": "그리디 알고리즘",     "cf_tag": "greedy",          "boj_tag": "greedy"},
    {"id": "graphs",          "label": "그래프 이론",         "cf_tag": "graphs",          "boj_tag": "graphs"},
    {"id": "brute-force",     "label": "완전 탐색",           "cf_tag": "brute force",     "boj_tag": "bruteforcing"},
    {"id": "dfs",             "label": "DFS / 탐색",          "cf_tag": "dfs and similar", "boj_tag": "dfs"},
    {"id": "binary-search",   "label": "이분 탐색",           "cf_tag": "binary search",   "boj_tag": "binary_search"},
    {"id": "shortest-path",   "label": "최단 경로",           "cf_tag": "shortest paths",  "boj_tag": "shortest_path"},
    {"id": "data-structures", "label": "자료 구조",           "cf_tag": "data structures", "boj_tag": "data_structures"},
    {"id": "strings",         "label": "문자열",              "cf_tag": "strings",         "boj_tag": "string"},
    {"id": "math",            "label": "수학",                "cf_tag": "math",            "boj_tag": "math"},
]


PER_BAND = 8               # 응답에 담는 밴드당 문제 수 (테마당 최대 24개)
POOL_PER_BAND = 20         # 캐시하는 밴드당 풀 크기 — 푼 문제 제외 후에도 PER_BAND를 채울 여유분
CACHE_TTL_SEC = 24 * 3600  # 대표 문제 목록은 하루면 충분

# 난이도 밴드 (쉬움/보통/어려움) — 밴드별 최다 풀이 순 상위를 뽑는다.
BOJ_BANDS = [(3, 8), (9, 13), (14, 18)]           # B3~S3 / S2~G3 / G2~P3
CF_BANDS = [(800, 1199), (1200, 1699), (1700, 2400)]


def get_theme_list() -> list[dict]:
    return [{"id": t["id"], "label": t["label"]} for t in THEMES]


def find_theme(theme_id: str) -> dict | None:
    return next((t for t in THEMES if t["id"] == theme_id), None)


def _fetch_boj_pool(boj_tag: str) -> list[list[dict]]:
    """밴드당 solved.ac 검색 1회(최다 풀이순) — 상위 POOL_PER_BAND개씩."""
    bands = []
    for lo, hi in BOJ_BANDS:
        found = search_problems_by_tag(boj_tag, lo, hi, exclude_ids=set())
        bands.append(found[:POOL_PER_BAND])
    return bands


def _fetch_cf_pool(cf_tag: str) -> list[list[dict]]:
    """CF 스냅샷 검색 1회(최다 풀이순) 후 레이팅 밴드로 버킷팅."""
    pool = search_cf_problems_by_tag(
        cf_tag, CF_BANDS[0][0], CF_BANDS[-1][1], exclude_refs=set(),
    )
    bands = []
    for lo, hi in CF_BANDS:
        in_band = [
            {"id": p["id"], "title": p["title"], "rating": p["rating"]}
            for p in pool
            if lo <= p["rating"] <= hi
        ]
        bands.append(in_band[:POOL_PER_BAND])
    return bands


def get_theme_problem_pool(platform: str, theme: dict) -> list[list[dict]] | None:
    """플랫폼·테마별 문제 풀(밴드 리스트). DB 캐시 우선, 외부 API 실패 시 만료 캐시 폴백.
    풀은 푼 문제 제외 '전' 원본이라 사용자 상태와 무관하게 캐시가 안정적이다."""
    key = f"themes:{platform}:{theme['id']}"
    cached = db.cache_get(key, CACHE_TTL_SEC)
    if cached is not None:
        return cached

    if platform == "boj":
        fresh = _fetch_boj_pool(theme["boj_tag"])
    else:
        fresh = _fetch_cf_pool(theme["cf_tag"])

    bands = fresh
    stale = db.cache_get_stale(key)
    # 밴드별로 따로 fetch하므로 일부만 실패할 수 있다(레이트리밋 등) — 실패(빈) 밴드는 이전 캐시로
    # 채워 부분 실패가 이미 좋은 밴드까지 지우지 않게 한다. 밴드 수가 다르면(설정 변경) 병합하지
    # 않는다 — zip이 짧은 쪽으로 잘라 잘린 결과를 캐시에 못박아 버린다.
    if stale is not None and len(stale) == len(fresh):
        bands = [new_band if new_band else old_band for new_band, old_band in zip(fresh, stale)]

    # 새로 받은 밴드가 하나라도 있을 때만 저장한다 — 전면 실패까지 저장하면 updated_at이 갱신돼
    # TTL(24시간) 내내 재시도가 멈춘 채 옛 데이터만 나간다.
    if any(fresh):
        db.cache_set(key, bands)
        return bands

    return stale


def build_theme_response(platform: str, theme: dict) -> dict:
    """풀에서 푼 문제를 제외하고 밴드당 PER_BAND개씩, 난이도 오름차순으로 응답을 만든다."""
    resp = {"theme": {"id": theme["id"], "label": theme["label"]}, "platform": platform}

    bands = get_theme_problem_pool(platform, theme)
    if bands is None:
        resp["problems"] = []
        resp["error"] = "문제 목록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요."
        return resp

    if platform == "boj":
        solved = db.get_solved_problem_ids()
        diff_field = "tier"
    else:
        solved = db.get_solved_cf_refs()
        diff_field = "rating"

    problems = []
    for band in bands:
        problems.extend([p for p in band if p["id"] not in solved][:PER_BAND])
    problems.sort(key=lambda p: p[diff_field])

    resp["problems"] = problems
    return resp
