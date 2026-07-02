import os
from fastapi import HTTPException

IS_DEMO = os.environ.get("DEMO_MODE", "false").lower() == "true"


def demo_block(message: str = "데모 버전에서는 지원되지 않는 기능입니다."):
    raise HTTPException(status_code=403, detail=f"[데모] {message}")


DEMO_PROBLEM_INFO = {
    "id": 1929,
    "platform": "boj",
    "problem_ref": "1929",
    "title": "소수 구하기",
    "tier": 7,
    "tier_name": "Silver IV",
    "tags": ["수학", "정수론", "소수 판별"],
}

DEMO_REVIEW_RESULT = {
    "efficiency": "ok",
    "complexity": "O(N√N)",
    "better_algorithm": "에라토스테네스의 체(Sieve of Eratosthenes)를 사용하면 O(N log log N)으로 개선 가능합니다.",
    "feedback": (
        "**전체 평가**\n"
        "기본적인 소수 판별 로직은 정확하게 구현되어 있습니다. "
        "각 수에 대해 √N까지만 나눠보는 최적화도 적용되어 있어 순수 브루트포스보다 효율적입니다.\n\n"
        "**개선 포인트**\n"
        "현재 코드는 M~N 범위의 각 숫자마다 소수 판별을 독립적으로 수행합니다. "
        "에라토스테네스의 체를 사용하면 한 번의 순회로 N까지의 모든 소수를 미리 구해둔 뒤 "
        "O(1)로 판별할 수 있어 훨씬 효율적입니다.\n\n"
        "**코드 스타일**\n"
        "변수명이 직관적이고 코드 흐름이 읽기 쉽습니다. "
        "is_prime 함수로 분리한 점도 좋은 패턴입니다."
    ),
    "strengths": [
        "√N 최적화가 올바르게 적용되어 있습니다",
        "함수 분리로 가독성이 높습니다",
    ],
    "weaknesses": [
        "N이 클수록 에라토스테네스의 체 대비 성능 차이가 커집니다",
    ],
}

DEMO_CF_PROBLEM = {
    "title": "Watermelon",
    "time_limit": "1 seconds",
    "memory_limit": "256 megabytes",
    "statement_sections_ko": {
        "statement": (
            "피트와 빌리는 수박 한 통을 샀습니다. "
            "두 사람은 수박을 정확히 두 부분으로 나누고 싶습니다. "
            "두 부분 모두 짝수 무게여야 하며, 각 부분은 비어 있지 않아야 합니다.\n\n"
            "수박의 무게가 $w$일 때, 이런 분할이 가능한지 판단하세요."
        ),
        "input": "첫 번째 줄에 수박의 무게 $w$가 주어집니다 ($1 \\le w \\le 100$).",
        "output": "분할이 가능하면 `YES`, 불가능하면 `NO`를 출력하세요.",
        "note": "$w = 8$이면 $2 + 6$ 또는 $4 + 4$ 등으로 나눌 수 있습니다.",
    },
    "samples": [
        {"input": "8", "output": "YES"},
        {"input": "1", "output": "NO"},
    ],
    "url": "https://codeforces.com/problemset/problem/4/A",
    "contest_id": "4",
    "index": "A",
}

DEMO_RECOMMENDATIONS = {
    "avg_tier": 0,
    "tier_name": "CF 1200",
    "tier_range": "CF 1000 ~ CF 1600",
    "weak_tags": ["greedy", "dp", "graphs"],
    "recommendations": [
        {
            "tag": "greedy",
            "tag_key": "greedy",
            "problems": [
                {
                    "id": "1285C",
                    "title": "Fadi and LCM",
                    "tier": 0,
                    "tier_name": "CF 1400",
                    "url": "https://codeforces.com/problemset/problem/1285/C",
                },
                {
                    "id": "1399C",
                    "title": "Boats Competition",
                    "tier": 0,
                    "tier_name": "CF 1300",
                    "url": "https://codeforces.com/problemset/problem/1399/C",
                },
            ],
        },
        {
            "tag": "dp",
            "tag_key": "dp",
            "problems": [
                {
                    "id": "837D",
                    "title": "Round Subset",
                    "tier": 0,
                    "tier_name": "CF 1700",
                    "url": "https://codeforces.com/problemset/problem/837/D",
                },
                {
                    "id": "1513C",
                    "title": "Add One",
                    "tier": 0,
                    "tier_name": "CF 1400",
                    "url": "https://codeforces.com/problemset/problem/1513/C",
                },
            ],
        },
        {
            "tag": "graphs",
            "tag_key": "graphs",
            "problems": [
                {
                    "id": "580C",
                    "title": "Kefa and Park",
                    "tier": 0,
                    "tier_name": "CF 1500",
                    "url": "https://codeforces.com/problemset/problem/580/C",
                },
            ],
        },
    ],
    "platform": "codeforces",
}

# 테마 데모 데이터 — 테마당 실측 대표 문제 3개(쉬움→어려움 사다리), 플랫폼 네이티브 난이도.
DEMO_THEME_LIST = [
    {"id": "dp", "label": "다이나믹 프로그래밍"},
    {"id": "greedy", "label": "그리디 알고리즘"},
    {"id": "graphs", "label": "그래프 이론"},
    {"id": "data-structures", "label": "자료 구조"},
]

_DEMO_THEME_LABELS = {t["id"]: t["label"] for t in DEMO_THEME_LIST}


def _demo_theme_response(platform: str, theme_id: str, problems: list[dict]) -> dict:
    return {
        "theme": {"id": theme_id, "label": _DEMO_THEME_LABELS[theme_id]},
        "platform": platform,
        "problems": problems,
    }


DEMO_THEME_PROBLEMS = {
    ("codeforces", "dp"): _demo_theme_response("codeforces", "dp", [
        {"id": "996A", "title": "Hit the Lottery", "rating": 800},
        {"id": "189A", "title": "Cut Ribbon", "rating": 1300},
        {"id": "466C", "title": "Number of Ways", "rating": 1700},
    ]),
    ("codeforces", "greedy"): _demo_theme_response("codeforces", "greedy", [
        {"id": "231A", "title": "Team", "rating": 800},
        {"id": "514A", "title": "Chewbacca and Number", "rating": 1200},
        {"id": "1365D", "title": "Solve The Maze", "rating": 1700},
    ]),
    ("codeforces", "graphs"): _demo_theme_response("codeforces", "graphs", [
        {"id": "500A", "title": "New Year Transportation", "rating": 1000},
        {"id": "520B", "title": "Two Buttons", "rating": 1400},
        {"id": "20C", "title": "Dijkstra?", "rating": 1900},
    ]),
    ("codeforces", "data-structures"): _demo_theme_response("codeforces", "data-structures", [
        {"id": "1703B", "title": "ICPC Balloons", "rating": 800},
        {"id": "4C", "title": "Registration System", "rating": 1300},
        {"id": "466C", "title": "Number of Ways", "rating": 1700},
    ]),
    ("boj", "dp"): _demo_theme_response("boj", "dp", [
        {"id": 2839, "title": "설탕 배달", "tier": 7, "tier_name": "Silver IV"},
        {"id": 1149, "title": "RGB거리", "tier": 10, "tier_name": "Silver I"},
        {"id": 2098, "title": "외판원 순회", "tier": 15, "tier_name": "Gold I"},
    ]),
    ("boj", "greedy"): _demo_theme_response("boj", "greedy", [
        {"id": 2839, "title": "설탕 배달", "tier": 7, "tier_name": "Silver IV"},
        {"id": 1931, "title": "회의실 배정", "tier": 11, "tier_name": "Gold V"},
        {"id": 1202, "title": "보석 도둑", "tier": 14, "tier_name": "Gold II"},
    ]),
    ("boj", "graphs"): _demo_theme_response("boj", "graphs", [
        {"id": 2606, "title": "바이러스", "tier": 8, "tier_name": "Silver III"},
        {"id": 1260, "title": "DFS와 BFS", "tier": 9, "tier_name": "Silver II"},
        {"id": 13460, "title": "구슬 탈출 2", "tier": 15, "tier_name": "Gold I"},
    ]),
    ("boj", "data-structures"): _demo_theme_response("boj", "data-structures", [
        {"id": 9012, "title": "괄호", "tier": 7, "tier_name": "Silver IV"},
        {"id": 1874, "title": "스택 수열", "tier": 9, "tier_name": "Silver II"},
        {"id": 1655, "title": "가운데를 말해요", "tier": 14, "tier_name": "Gold II"},
    ]),
}

DEMO_GITHUB_STATUS = {
    "connected": True,
    "username": "demo_user",
    "target_repo": "demo_user/algorithm-solutions",
}

DEMO_REPOS = [
    "demo_user/algorithm-solutions",
    "demo_user/competitive-programming",
]

DEMO_REPORT = (
    "## 강점 영역\n"
    "- **그리디 / 정렬**: ATM, 보물 등에서 정렬 기반 그리디 아이디어를 정확히 적용하고 있습니다.\n"
    "- **그래프 탐색(DFS/BFS)**: DFS와 BFS, 미로 탐색에서 방문 관리와 탐색 순서를 안정적으로 구현합니다.\n\n"
    "## 취약 영역\n"
    "- **다이나믹 프로그래밍**: 피보나치 함수·파도반 수열에서 재귀에 머물러 메모이제이션/반복 DP 전환이 더디게 나타납니다.\n"
    "- **시간복잡도 최적화**: list.pop(0) 사용 등 자료구조 선택에서 불필요한 비용이 반복됩니다.\n\n"
    "## 학습 우선순위\n"
    "1. 점화식 도출 → 반복 DP 구현 패턴을 집중적으로 연습하세요.\n"
    "2. deque, 누적합 등 상수 시간 최적화 도구를 손에 익히세요.\n\n"
    "## 성장 방향\n"
    "기본기는 탄탄하므로, DP와 자료구조 최적화를 보완하면 Gold 상위 난이도로 무리 없이 올라갈 수 있습니다."
)
