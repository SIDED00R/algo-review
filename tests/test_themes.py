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
