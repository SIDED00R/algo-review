"""테마 문제 풀 캐싱 — 밴드별 부분 실패가 기존에 캐시된 좋은 밴드를 지우지 않는지."""
import db
import themes


def test_partial_band_failure_preserves_previously_cached_bands(monkeypatch):
    theme = themes.find_theme("dp")
    key = themes._pool_cache_key("boj", theme)

    full = [[{"id": 1}], [{"id": 2}], [{"id": 3}]]
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: full)
    # 매 호출마다 재조회를 유도한다(신선 캐시가 있으면 아예 fetch를 안 타 테스트가 무의미해진다).
    monkeypatch.setattr(db, "cache_get", lambda k, max_age_sec: None)

    assert themes.get_theme_problem_pool("boj", theme) == full
    assert db.cache_get_stale(key) == full  # 방금 값이 stale 캐시에도 남았다

    # 밴드 0·2 만 레이트리밋 등으로 일시 실패([[], [...], []]) — 밴드 1 만 성공했다.
    partial = [[], [{"id": 99}], []]
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: partial)

    merged = themes.get_theme_problem_pool("boj", theme)
    # 실패한 밴드(0, 2)는 이전 캐시로 채워지고, 성공한 밴드(1)만 새 값으로 갱신된다.
    assert merged == [[{"id": 1}], [{"id": 99}], [{"id": 3}]]


def test_total_failure_does_not_refresh_cache_timestamp(monkeypatch):
    """전면 실패까지 저장하면 updated_at 이 갱신돼 TTL 내내 재시도가 멈춘다."""
    theme = themes.find_theme("graphs")
    full = [[{"id": 1}], [{"id": 2}], [{"id": 3}]]
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: full)
    monkeypatch.setattr(db, "cache_get", lambda k, max_age_sec: None)
    themes.get_theme_problem_pool("boj", theme)

    writes = []
    monkeypatch.setattr(db, "cache_set", lambda k, v: writes.append((k, v)))
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: [[], [], []])   # 전면 실패

    assert themes.get_theme_problem_pool("boj", theme) == full, "폴백으로 이전 값은 돌려줘야 한다"
    assert writes == [], "전면 실패인데 캐시를 다시 써서 재시도를 24시간 막았다"


def test_band_count_change_skips_merge(monkeypatch):
    """밴드 수가 바뀌면 zip 이 짧은 쪽으로 잘라 잘린 결과를 캐시에 못박는다 — 병합하지 않아야 한다."""
    theme = themes.find_theme("strings")
    monkeypatch.setattr(db, "cache_get", lambda k, max_age_sec: None)
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: [[{"id": 1}], [{"id": 2}], [{"id": 3}]])
    themes.get_theme_problem_pool("boj", theme)

    four = [[{"id": 9}], [{"id": 8}], [{"id": 7}], [{"id": 6}]]   # 밴드 4개로 늘어난 배포
    monkeypatch.setattr(themes, "_fetch_boj_pool", lambda tag: four)
    assert themes.get_theme_problem_pool("boj", theme) == four, "밴드가 3개로 잘렸다"


def test_response_caps_same_difficulty_at_two(monkeypatch):
    """밴드 안에서 풀이 수 상위가 한 난이도에 몰려도 같은 난이도는 2개까지만 담는다."""
    theme = themes.find_theme("dp")
    band = [{"id": f"{i}A", "title": "t", "rating": 800} for i in range(5)] + [
        {"id": "9B", "title": "t", "rating": 900},
        {"id": "9C", "title": "t", "rating": 1000},
    ]
    monkeypatch.setattr(themes, "get_theme_problem_pool", lambda platform, t: [band, [], []])
    monkeypatch.setattr(themes, "_solved_set", lambda platform: {"0A"})

    ids = [p["id"] for p in themes.build_theme_response("codeforces", theme)["problems"]]
    # 푼 0A 를 뺀 뒤 800 은 앞에서부터 2개(1A·2A)만 남는다.
    assert ids == ["1A", "2A", "9B", "9C"]


def test_cf_pool_keeps_other_difficulties_beyond_crowded_top(monkeypatch):
    """풀은 난이도별 상한으로 담는다 — 한 난이도가 풀이 수 상위를 채워도 다른 난이도가 풀에 남는다."""
    cap = themes.POOL_PER_DIFFICULTY
    crowded = [{"id": f"{i}A", "title": "t", "rating": 800} for i in range(cap + 10)]
    other = [{"id": "99B", "title": "t", "rating": 1100}]
    monkeypatch.setattr(themes, "search_cf_problems_by_tag", lambda *a, **k: crowded + other)

    easy = themes._fetch_cf_pool("dp")[0]
    assert [p["id"] for p in easy] == [f"{i}A" for i in range(cap)] + ["99B"]


def test_boj_pool_survives_a_user_who_solved_the_most_popular(monkeypatch):
    """많이 푼 사용자는 난이도별 풀이 수 상위를 이미 풀었다 — 풀이 그보다 깊어야 그 난이도가 남는다."""
    theme = themes.find_theme("math")
    band = [{"id": 1000 + i, "title": "t", "tier": 3} for i in range(30)]
    monkeypatch.setattr(themes, "search_problems_by_tag", lambda *a, **k: band)
    pool = themes._fetch_boj_pool(theme["boj_tag"])

    monkeypatch.setattr(themes, "get_theme_problem_pool", lambda platform, t: pool)
    monkeypatch.setattr(themes, "_solved_set", lambda platform: {1000 + i for i in range(10)})

    ids = [p["id"] for p in themes.build_theme_response("boj", theme)["problems"]]
    assert ids[:2] == [1010, 1011]


def test_theme_list_is_per_platform():
    ids = {p: [t["id"] for t in themes.get_theme_list(p)] for p in ("boj", "codeforces", "leetcode")}
    assert "sql" in ids["leetcode"]
    assert "sql" not in ids["boj"] and "sql" not in ids["codeforces"]
    assert ids["boj"] == ids["codeforces"]


def test_lc_pool_buckets_three_difficulties_and_the_response_caps_at_band_size(monkeypatch):
    pool = [{"id": f"p{i}", "problem_id": i, "title": "t", "tier": 1 + i % 3, "tier_name": "x", "url": "u"}
            for i in range(60)]
    monkeypatch.setattr(themes, "search_lc_problems_by_tag", lambda *a, **k: pool)
    bands = themes._fetch_lc_pool("database")
    assert [len(b) for b in bands] == [20, 20, 20]

    monkeypatch.setattr(themes, "get_theme_problem_pool", lambda platform, t: bands)
    monkeypatch.setattr(themes, "_solved_set", lambda platform: {"p0"})
    resp = themes.build_theme_response("leetcode", themes.find_theme("sql"))
    # LeetCode 는 밴드 하나가 난이도 하나라 같은 난이도 상한이 밴드 크기(8)다.
    assert sorted(p["tier"] for p in resp["problems"]) == [1] * 8 + [2] * 8 + [3] * 8
    assert "p0" not in [p["id"] for p in resp["problems"]]


def test_sql_theme_exists_only_where_the_platform_has_it(minimal_app):
    from routes import themes as themes_route
    client = minimal_app(themes_route.router)
    assert client.get("/api/themes/sql/problems", params={"platform": "boj"}).status_code == 404
    assert [t["id"] for t in client.get("/api/themes", params={"platform": "leetcode"}).json()["themes"]][-1] == "sql"
    assert "sql" not in [t["id"] for t in client.get("/api/themes", params={"platform": "boj"}).json()["themes"]]
    assert client.get("/api/themes", params={"platform": "atcoder"}).status_code == 400


def test_warmup_skips_themes_the_platform_does_not_have(monkeypatch):
    import asyncio
    import warmup
    seen = []
    monkeypatch.setattr(warmup, "WARMUP_DELAY_SEC", 0)
    monkeypatch.setattr(themes, "theme_pool_is_fresh",
                        lambda platform, theme: seen.append((platform, theme["id"])) or True)
    asyncio.run(warmup.warm_theme_caches())
    assert ("leetcode", "sql") in seen
    assert ("boj", "sql") not in seen and ("codeforces", "sql") not in seen
