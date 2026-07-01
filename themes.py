from clients import search_problems_by_tag

# 테마별 문제 둘러보기 — 사용자 데이터와 무관하게 알고리즘 분야별 대표 문제를 제공한다.
# tag_key 는 solved.ac API 의 태그 식별자.
THEMES = [
    {"label": "다이나믹 프로그래밍", "tag_key": "dp"},
    {"label": "그리디 알고리즘",     "tag_key": "greedy"},
    {"label": "그래프 이론",         "tag_key": "graphs"},
    {"label": "너비 우선 탐색(BFS)", "tag_key": "bfs"},
    {"label": "깊이 우선 탐색(DFS)", "tag_key": "dfs"},
    {"label": "이분 탐색",           "tag_key": "binary_search"},
    {"label": "최단 경로",           "tag_key": "dijkstra"},
    {"label": "자료 구조",           "tag_key": "data_structures"},
    {"label": "문자열",              "tag_key": "string"},
    {"label": "수학",                "tag_key": "math"},
]

PROBLEMS_PER_THEME = 3
_THEME_TIER_MIN = 1   # Bronze V
_THEME_TIER_MAX = 30  # Ruby I (전 구간)


def get_theme_problems() -> list[dict]:
    """각 테마 태그에서 가장 많이 풀린(대표) 문제 상위 N개를 모아 반환한다."""
    results = []
    for theme in THEMES:
        problems = search_problems_by_tag(
            tag_key=theme["tag_key"],
            min_tier=_THEME_TIER_MIN,
            max_tier=_THEME_TIER_MAX,
            exclude_ids=set(),
        )[:PROBLEMS_PER_THEME]
        for p in problems:
            p["url"] = f"https://boj.kr/{p['id']}"
        results.append({
            "label": theme["label"],
            "tag_key": theme["tag_key"],
            "problems": problems,
        })
    return results
