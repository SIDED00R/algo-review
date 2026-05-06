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

DEMO_GITHUB_STATUS = {
    "connected": True,
    "username": "demo_user",
    "target_repo": "demo_user/algorithm-solutions",
}

DEMO_REPOS = [
    "demo_user/algorithm-solutions",
    "demo_user/competitive-programming",
]
