"""LeetCode 가 라우터 공용 헬퍼·통계·리포트에 배선되는지."""
import pytest
from fastapi import HTTPException

import clients as api_client
import db
from clients.utils import _ext_to_language, get_file_extension, get_problem_url
from routes import helpers, report as report_route, stats as stats_route


def _lc_review(problem_id, slug, tier, tags, efficiency="good"):
    label = {1: "Easy", 2: "Medium", 3: "Hard"}[tier]
    db.save_review(problem_id=problem_id, title=slug, tier=tier, tier_name=f"LeetCode {label}", tags=tags,
                   code="c", feedback="", efficiency=efficiency, platform="leetcode", problem_ref=slug)


def test_problem_ref_is_normalized_to_a_slug_and_numbers_are_rejected():
    assert helpers.require_problem_ref("leetcode", "https://leetcode.com/problems/Two-Sum/") == "two-sum"
    with pytest.raises(HTTPException) as e:
        helpers.require_problem_ref("leetcode", "175")
    assert e.value.status_code == 400


def test_solution_folder_uses_difficulty_and_slug():
    assert helpers.build_solution_target("leetcode", "two-sum", "Two Sum", "LeetCode Easy") == \
        ("LeetCode/Easy/two-sum. Two Sum", "[LeetCode] two-sum. Two Sum")
    assert helpers.build_solution_target("leetcode", "x", "T", "")[0] == "LeetCode/Unrated/x. T"


def test_problem_url_and_sql_extension_round_trip():
    assert get_problem_url("leetcode", "Two-Sum") == "https://leetcode.com/problems/two-sum/"
    assert get_file_extension("MySQL") == ".sql"
    assert get_file_extension("postgresql") == ".sql"
    assert _ext_to_language("two-sum.sql") == "MySQL"


def test_average_difficulty_for_leetcode_rounds_to_a_label():
    assert helpers.average_difficulty("leetcode") == (2.0, False, "N/A")
    _lc_review(1, "two-sum", 1, ["Array"])
    _lc_review(72, "edit-distance", 2, ["String"])
    assert helpers.average_difficulty("leetcode") == (1.5, True, "LeetCode Medium")
    # BOJ 평균은 LC 행을 세지 않는다.
    assert helpers.average_difficulty("boj")[1] is False


def test_average_difficulty_rounds_half_up_like_the_frontend_badge():
    """평균 2.5 는 서버 라벨도 Hard 여야 한다 — 프런트 배지는 Math.round(2.5)=3(Hard) 이고,
    파이썬 round(2.5) 는 2 라 라벨만 Medium 이 되어 빨간 배지에 Medium 글자가 들어간다."""
    _lc_review(72, "edit-distance", 2, ["String"])
    _lc_review(4, "median-of-two-sorted-arrays", 3, ["Array"])
    assert helpers.average_difficulty("leetcode") == (2.5, True, "LeetCode Hard")


def test_push_review_bundle_scrapes_lc_sections_and_names_the_sql_file(monkeypatch):
    pushed = {}

    def _push(repo, token, files, msg):
        pushed["files"] = {f["path"]: f["content"] for f in files}
        return True

    monkeypatch.setattr(api_client, "get_lc_problem_sections",
                        lambda ref: {"description": "테이블 설명", "input": "", "output": ""})
    monkeypatch.setattr(api_client, "push_files_to_github", _push)

    folder = helpers.push_review_bundle(
        "u/r", "t", platform="leetcode", problem_ref="combine-two-tables", title="Combine Two Tables",
        tier_name="LeetCode Easy", tags=["Database"], language="MySQL", code="SELECT 1",
        require_sections=False)
    assert folder == "LeetCode/Easy/combine-two-tables. Combine Two Tables"
    readme = pushed["files"][f"{folder}/README.md"]
    assert f"{folder}/combine-two-tables.sql" in pushed["files"]
    assert "## 문제 설명\n\n테이블 설명" in readme
    assert "## 입력" not in readme and "## 출력" not in readme
    assert "[문제 링크](https://leetcode.com/problems/combine-two-tables/)" in readme


def test_stats_and_report_for_leetcode(minimal_app, monkeypatch):
    _lc_review(1, "two-sum", 1, ["Array"])
    _lc_review(175, "combine-two-tables", 2, ["Database"], efficiency="poor")

    body = minimal_app(stats_route.router).get("/api/stats", params={"platform": "leetcode"}).json()
    assert (body["platform"], body["avg_tier"], body["avg_tier_name"], body["total_reviews"]) == \
        ("leetcode", 1.5, "LeetCode Medium", 2)
    assert {s["tag"]: s["poor_count"] for s in body["tag_stats"]} == {"Array": 0, "Database": 1}
    assert minimal_app(stats_route.router).get("/api/stats", params={"platform": "boj"}).json()["total_reviews"] == 0

    seen = {}
    monkeypatch.setattr(report_route, "require_openai_key", lambda: None)
    monkeypatch.setattr(report_route.analyzer, "get_cumulative_analysis",
                        lambda tag_stats, history: seen.update(tags=sorted(s["tag"] for s in tag_stats)) or "리포트")
    r = minimal_app(report_route.router).get("/api/report", params={"platform": "leetcode"})
    assert r.status_code == 200 and r.json() == {"report": "리포트"}
    assert seen == {"tags": ["Array", "Database"]}
