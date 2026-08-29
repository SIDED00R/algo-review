import db


_REVIEWS = [
    dict(problem_id=11399, title="ATM", tier=8, tier_name="Silver III",
         tags=["그리디", "정렬"], platform="boj", problem_ref="11399",
         efficiency="good", complexity="O(N log N)",
         feedback="정렬 후 누적합으로 최솟값을 구하는 전형적인 그리디 풀이입니다. 로직이 간결하고 정확합니다.",
         strengths=["핵심 아이디어를 바로 파악하여 깔끔하게 구현했습니다"],
         weaknesses=[]),
    dict(problem_id=1026, title="보물", tier=6, tier_name="Silver V",
         tags=["그리디", "정렬", "수학"], platform="boj", problem_ref="1026",
         efficiency="good", complexity="O(N log N)",
         feedback="A는 오름차순, B는 내림차순으로 정렬해 곱의 합을 최소화하는 그리디 전략이 정확합니다.",
         strengths=["정렬 기반 그리디 아이디어를 잘 적용했습니다"],
         weaknesses=[]),
    dict(problem_id=1003, title="피보나치 함수", tier=7, tier_name="Silver IV",
         tags=["다이나믹 프로그래밍"], platform="boj", problem_ref="1003",
         efficiency="ok", complexity="O(N)",
         better_algorithm="메모이제이션 대신 반복문 DP로 구현하면 재귀 오버헤드를 없앨 수 있습니다.",
         feedback="메모이제이션으로 중복 계산을 줄인 점은 좋으나, 반복문 DP가 더 효율적입니다.",
         strengths=["중복 계산 방지를 위한 캐싱 개념을 적용했습니다"],
         weaknesses=["재귀 호출 오버헤드가 남아 있습니다"]),
    dict(problem_id=9461, title="파도반 수열", tier=10, tier_name="Silver I",
         tags=["다이나믹 프로그래밍", "수학"], platform="boj", problem_ref="9461",
         efficiency="poor", complexity="O(2^N)",
         better_algorithm="점화식 dp[n] = dp[n-2] + dp[n-3]을 사용하면 O(N)으로 해결됩니다.",
         feedback="재귀만으로 풀어 지수 시간이 소요됩니다. DP 점화식을 도출하는 연습이 필요합니다.",
         strengths=["문제 구조를 재귀적으로 파악한 점은 좋습니다"],
         weaknesses=["메모이제이션 또는 반복 DP 미적용으로 지수 시간 복잡도입니다"]),
    dict(problem_id=1260, title="DFS와 BFS", tier=9, tier_name="Silver II",
         tags=["그래프 이론", "DFS", "BFS"], platform="boj", problem_ref="1260",
         efficiency="good", complexity="O(V+E)",
         feedback="DFS·BFS 모두 정석적으로 구현했습니다. 방문 배열 관리도 정확합니다.",
         strengths=["DFS·BFS를 올바르게 구현했습니다", "방문 순서가 문제 조건에 맞습니다"],
         weaknesses=[]),
    dict(problem_id=2178, title="미로 탐색", tier=9, tier_name="Silver II",
         tags=["그래프 이론", "BFS"], platform="boj", problem_ref="2178",
         efficiency="ok", complexity="O(NM)",
         better_algorithm="큐를 deque로 바꾸면 popleft()가 O(1)이 됩니다.",
         feedback="BFS 최단 경로 로직은 맞지만 list.pop(0) 사용으로 불필요한 비용이 있습니다.",
         strengths=["BFS로 최단 경로를 찾는 접근이 정확합니다"],
         weaknesses=["list.pop(0) 대신 deque.popleft() 사용을 권장합니다"]),
    dict(problem_id=1654, title="랜선 자르기", tier=11, tier_name="Gold V",
         tags=["이분 탐색"], platform="boj", problem_ref="1654",
         efficiency="good", complexity="O(K log L)",
         feedback="이분 탐색 범위 설정과 조건 판별이 정확합니다. 전형적인 파라메트릭 서치 패턴입니다.",
         strengths=["이분 탐색 경계 조건이 정확합니다"],
         weaknesses=[]),
    dict(problem_id=71001, title="Watermelon", tier=0, tier_name="Codeforces 800",
         tags=["greedy", "math", "brute force"], platform="codeforces", problem_ref="4A",
         efficiency="good", complexity="O(1)",
         feedback="짝수이면서 2보다 큰지 확인하는 단순 조건으로 정확히 해결했습니다.",
         strengths=["핵심 조건을 정확히 파악했습니다"],
         weaknesses=[]),
    dict(problem_id=71101, title="Way Too Long Words", tier=0, tier_name="Codeforces 800",
         tags=["strings", "implementation"], platform="codeforces", problem_ref="71A",
         efficiency="good", complexity="O(N)",
         feedback="길이 조건 분기와 약어 생성 로직이 깔끔합니다.",
         strengths=["조건 분기를 간결하게 처리했습니다"],
         weaknesses=[]),
    dict(problem_id=71201, title="Next Round", tier=0, tier_name="Codeforces 900",
         tags=["implementation"], platform="codeforces", problem_ref="158B",
         efficiency="ok", complexity="O(N)",
         better_algorithm="k번째 점수를 기준으로 필터링하면 더 간결하게 작성할 수 있습니다.",
         feedback="로직은 맞지만 조건 처리를 좀 더 간결하게 줄일 수 있습니다.",
         strengths=["경계 조건을 올바르게 처리했습니다"],
         weaknesses=["코드를 더 간결하게 작성할 여지가 있습니다"]),
    dict(problem_id=71301, title="Theatre Square", tier=0, tier_name="Codeforces 1000",
         tags=["math"], platform="codeforces", problem_ref="1A",
         efficiency="poor", complexity="O(NM)",
         better_algorithm="ceil(n/a) * ceil(m/a)로 O(1)에 계산할 수 있습니다.",
         feedback="중첩 루프로 각 타일을 시뮬레이션해 시간 초과가 발생합니다. 수식으로 바로 계산하세요.",
         strengths=["문제 의도를 파악했습니다"],
         weaknesses=["O(NM) 시뮬레이션 대신 O(1) 수식으로 해결해야 합니다"]),
]

_SOLVED = [
    dict(problem_id=1000, title="A+B", tier=1, tier_name="Bronze V",
         tags=["수학", "구현"], platform="boj", problem_ref="1000", language="Python 3"),
    dict(problem_id=2557, title="Hello World", tier=1, tier_name="Bronze V",
         tags=["구현"], platform="boj", problem_ref="2557", language="Python 3"),
    dict(problem_id=10950, title="A+B - 3", tier=2, tier_name="Bronze IV",
         tags=["수학", "구현"], platform="boj", problem_ref="10950", language="Python 3"),
    dict(problem_id=2750, title="수 정렬하기", tier=3, tier_name="Bronze III",
         tags=["정렬"], platform="boj", problem_ref="2750", language="Python 3"),
    dict(problem_id=1929, title="소수 구하기", tier=7, tier_name="Silver IV",
         tags=["수학", "정수론", "소수 판별"], platform="boj", problem_ref="1929", language="Python 3"),
    dict(problem_id=70001, title="Watermelon", tier=0, tier_name="Codeforces 800",
         tags=["greedy", "math"], platform="codeforces", problem_ref="4A", language="Python 3"),
    dict(problem_id=70002, title="Way Too Long Words", tier=0, tier_name="Codeforces 800",
         tags=["strings"], platform="codeforces", problem_ref="71A", language="Python 3"),
    dict(problem_id=70003, title="Next Round", tier=0, tier_name="Codeforces 900",
         tags=["implementation"], platform="codeforces", problem_ref="158B", language="Python 3"),
]


def seed():
    db.run_migrations()

    if db.get_total_review_count() > 0:
        # save_review 는 append-only 다. 이미 시드됐으면 건너뛴다.
        return

    for r in _REVIEWS:
        db.save_review(
            problem_id=r["problem_id"],
            title=r["title"],
            tier=r["tier"],
            tier_name=r["tier_name"],
            tags=r["tags"],
            code="# 데모 코드",
            feedback=r["feedback"],
            efficiency=r["efficiency"],
            complexity=r.get("complexity", ""),
            better_algorithm=r.get("better_algorithm", ""),
            strengths=r.get("strengths", []),
            weaknesses=r.get("weaknesses", []),
            platform=r["platform"],
            problem_ref=r["problem_ref"],
        )

    for s in _SOLVED:
        db.save_solved_problem(
            problem_id=s["problem_id"],
            title=s["title"],
            tier=s["tier"],
            tier_name=s["tier_name"],
            tags=s["tags"],
            code="",
            language=s.get("language", ""),
            platform=s["platform"],
            problem_ref=s["problem_ref"],
        )

    db.save_github_settings(access_token="demo_token", github_username="demo_user")
    db.update_github_target_repo("demo_user/algorithm-solutions")
