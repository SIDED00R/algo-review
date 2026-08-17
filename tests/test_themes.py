"""테마 문제 풀 캐싱 — 밴드별 부분 실패가 기존에 캐시된 좋은 밴드를 지우지 않는지 회귀."""
import db
import themes


def test_partial_band_failure_preserves_previously_cached_bands(monkeypatch):
    theme = themes.find_theme("dp")
    key = f"themes:boj:{theme['id']}"

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
