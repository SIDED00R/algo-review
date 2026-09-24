"""LeetCode 추천 — 3단계 난이도 밴드와 slug 제외가 배선되는지."""
import db
import recommender
from routes import recommend as recommend_route


def _lc_review(problem_id, slug, tier, tags, efficiency="good"):
    label = {1: "Easy", 2: "Medium", 3: "Hard"}[tier]
    db.save_review(problem_id=problem_id, title=slug, tier=tier, tier_name=f"LeetCode {label}",
                   tags=tags, code="c", feedback="", efficiency=efficiency,
                   platform="leetcode", problem_ref=slug)


def test_lc_bands_follow_the_three_difficulties():
    assert recommender._lc_bands(1.2) == (1, 1, 2, 3)
    assert recommender._lc_bands(1.5) == (2, 2, 3, 3)
    # 2.5 는 half-up 으로 Hard — 프런트 Math.round(2.5)=3 과 같아야 배지·범위가 맞는다(round() 는 2 다).
    assert recommender._lc_bands(2.5) == (3, 3, 3, 3)
    assert recommender.lc_difficulty_range_description(2.5) == "Hard ~ Hard"
    assert recommender._lc_bands(2.6) == (3, 3, 3, 3)
    assert recommender._lc_bands(10.0) == (3, 3, 3, 3), "BOJ 척도 기본값이 들어와도 Hard 로 클램프한다"
    assert recommender.lc_difficulty_range_description(1.0) == "Easy ~ Hard"
    assert recommender.lc_difficulty_range_description(3.0) == "Hard ~ Hard"


def test_leetcode_recommendations_search_same_and_harder_bands_and_dedupe(monkeypatch):
    calls = []

    def _search(tag, lo, hi, exclude):
        calls.append((tag, lo, hi, set(exclude)))
        return [{"id": f"{tag}-{lo}{hi}-a", "problem_id": 1, "title": "t", "tier": lo, "tier_name": "Easy", "url": "u"},
                {"id": f"{tag}-{lo}{hi}-b", "problem_id": 2, "title": "t", "tier": hi, "tier_name": "Hard", "url": "u"}]

    monkeypatch.setattr(recommender, "search_lc_problems_by_tag", _search)
    _lc_review(1, "two-sum", 1, ["Array"])

    recs = recommender.get_recommendations(["Array"], platform="leetcode", extra_exclude={"x"}, avg_difficulty=1.0)
    assert calls == [("Array", 1, 1, {"two-sum", "x"}), ("Array", 2, 3, {"two-sum", "x"})]
    assert [p["id"] for p in recs[0]["problems"]] == ["Array-11-a", "Array-23-a", "Array-23-b"]

    # Hard 평균이면 same·hard 밴드가 같다 — 같은 문제가 두 번 나오면 안 된다.
    calls.clear()
    recs = recommender.get_recommendations(["Array"], platform="leetcode", avg_difficulty=3.0)
    assert [p["id"] for p in recs[0]["problems"]] == ["Array-33-a", "Array-33-b"]


def test_recommend_route_reports_leetcode_difficulty_and_lowercases_excludes(minimal_app, monkeypatch):
    _lc_review(1, "two-sum", 1, ["Array"])
    _lc_review(175, "combine-two-tables", 2, ["Database"], efficiency="poor")
    seen = {}

    def _recs(weak_tags, platform, extra_exclude, avg_difficulty):
        seen.update(platform=platform, extra_exclude=set(extra_exclude), avg=avg_difficulty)
        return []

    monkeypatch.setattr(recommend_route.recommender, "get_recommendations", _recs)
    body = minimal_app(recommend_route.router).get(
        "/api/recommend", params={"platform": "leetcode", "exclude": "Edit-Distance,Two-Sum"}).json()
    assert (body["platform"], body["avg_tier"], body["tier_name"], body["tier_range"]) == \
        ("leetcode", 1.5, "LeetCode Medium", "Medium ~ Hard")
    assert seen == {"platform": "leetcode", "extra_exclude": {"edit-distance", "two-sum"}, "avg": 1.5}


def test_recommend_route_without_leetcode_history_uses_medium_bands(minimal_app):
    body = minimal_app(recommend_route.router).get("/api/recommend", params={"platform": "leetcode"}).json()
    assert body["weak_tags"] == [] and body["recommendations"] == []
    assert (body["avg_tier"], body["tier_name"], body["tier_range"]) == (0, "N/A", "Medium ~ Hard")
