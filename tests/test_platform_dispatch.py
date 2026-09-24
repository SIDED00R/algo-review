"""플랫폼 분기가 미지원 값을 명시적으로 거부하는지.

분기가 2갈래 else 로 남으면 새 플랫폼 문자열이 BOJ 나 CF 경로로 조용히 처리된다 —
URL 이 boj.kr 이 되거나 폴더가 Codeforces/ 가 되는 식이다. 각 함수를 실제로 호출한다.
"""
import pytest
from fastapi import HTTPException

import analyzer
import recommender
import themes
from clients.utils import get_problem_url
from routes import helpers, problem_resolve

_UNKNOWN = "atcoder"


def _unsupported(exc) -> bool:
    return "지원하지 않는 플랫폼" in str(exc)


def test_problem_url_does_not_fall_back_to_boj():
    with pytest.raises(ValueError) as e:
        get_problem_url(_UNKNOWN, "1")
    assert _unsupported(e.value)


def test_solution_folder_does_not_fall_back_to_codeforces():
    with pytest.raises(ValueError) as e:
        helpers.build_solution_target(_UNKNOWN, "1", "title", "")
    assert _unsupported(e.value)


def test_problem_ref_validation_rejects_with_400():
    with pytest.raises(HTTPException) as e:
        helpers.require_problem_ref(_UNKNOWN, "1")
    assert e.value.status_code == 400
    assert _unsupported(e.value.detail)


def test_average_difficulty_rejects():
    with pytest.raises(ValueError) as e:
        helpers.average_difficulty(_UNKNOWN)
    assert _unsupported(e.value)


def test_resolve_problem_info_rejects_with_400():
    with pytest.raises(HTTPException) as e:
        problem_resolve.resolve_problem_info(_UNKNOWN, 1, "1")
    assert e.value.status_code == 400
    assert _unsupported(e.value.detail)


def test_resolve_statement_rejects():
    with pytest.raises(ValueError) as e:
        problem_resolve.resolve_statement(_UNKNOWN, {"problem_ref": "1"})
    assert _unsupported(e.value)


def test_analyzer_rejects_before_calling_the_llm(monkeypatch):
    class _Completions:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("미지원 플랫폼인데 LLM 이 호출됐다")

    class _Client:
        chat = type("_Chat", (), {"completions": _Completions})

    monkeypatch.setattr(analyzer, "get_client", lambda: _Client)
    info = {"platform": _UNKNOWN, "tags": [], "title": "t", "tier": 0, "tier_name": ""}
    with pytest.raises(ValueError) as e:
        analyzer.analyze_code(info, "", "print(1)")
    assert _unsupported(e.value)


def test_recommender_rejects():
    with pytest.raises(ValueError) as e:
        recommender.get_recommendations(["dp"], platform=_UNKNOWN, avg_difficulty=1)
    assert _unsupported(e.value)


def test_theme_pool_rejects():
    with pytest.raises(ValueError) as e:
        themes.get_theme_problem_pool(_UNKNOWN, themes.find_theme("dp"))
    assert _unsupported(e.value)


def test_theme_solved_set_rejects():
    with pytest.raises(ValueError) as e:
        themes._solved_set(_UNKNOWN)
    assert _unsupported(e.value)


def test_theme_response_rejects():
    with pytest.raises(ValueError) as e:
        themes.build_theme_response(_UNKNOWN, themes.find_theme("dp"))
    assert _unsupported(e.value)


# 라우터의 else 분기. require_platform 이 입구에서 막으므로 그것을 통과시킨 뒤에도
# BOJ 응답이 아니라 400 이 나와야 한다.

def test_stats_route_does_not_fall_back_to_boj(minimal_app, monkeypatch):
    from routes import stats as stats_route
    monkeypatch.setattr(stats_route, "require_platform", lambda v: v)
    r = minimal_app(stats_route.router).get("/api/stats", params={"platform": _UNKNOWN})
    assert r.status_code == 400
    assert _unsupported(r.json()["detail"])


def test_report_route_does_not_fall_back_to_codeforces(minimal_app, monkeypatch):
    from routes import report as report_route
    monkeypatch.setattr(report_route, "require_platform", lambda v: v)
    monkeypatch.setattr(report_route, "require_openai_key", lambda: None)
    r = minimal_app(report_route.router).get("/api/report", params={"platform": _UNKNOWN})
    assert r.status_code == 400
    assert _unsupported(r.json()["detail"])


def test_recommend_route_does_not_fall_back_to_boj(minimal_app, monkeypatch):
    from routes import recommend as recommend_route
    monkeypatch.setattr(recommend_route, "require_platform", lambda v: v)
    r = minimal_app(recommend_route.router).get("/api/recommend", params={"platform": _UNKNOWN})
    assert r.status_code == 400
    assert _unsupported(r.json()["detail"])
