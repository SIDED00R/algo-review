"""/api/review-imported 의 본문 해석과 데모 가드.

가져온 기록 AI 리뷰는 리뷰·재리뷰와 **같은 해석기**로 문제 본문을 얻어야 한다.
수집 함수를 직접 부르면 실패 시 반환되는 문자열(`"크롤링 실패: 404 …"`)이 그대로 LLM
프롬프트의 문제 설명 자리에 박히고, 그 결과가 DB 에 영구 저장된다. BOJ 는 acmicpc.net
종료로 수집이 상시 실패하므로 매 리뷰가 그 상태가 된다.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import db
from routes import problem_resolve
from routes import solved as solved_route

_SOLVED_BOJ = dict(
    problem_id=1000, title="A+B", tier=1, tier_name="Bronze V",
    tags=["arithmetic"], code="print(1)", language="Python 3",
    platform="boj", problem_ref="1000",
)
_RESULT = {
    "feedback": "좋다", "efficiency": "good", "complexity": "O(1)",
    "better_algorithm": "", "strengths": ["간결"], "weaknesses": [],
}


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(solved_route, "IS_DEMO", False)
    monkeypatch.setattr(solved_route.settings, "openai_api_key", "sk-test")
    return minimal_app(solved_route.router)


def _seed_boj():
    db.save_solved_problem(**_SOLVED_BOJ)


def _capture(seen):
    """analyze_code 대역 — 인자를 seen 에 기록하고 고정 결과를 돌려준다.

    한 줄짜리 대역(`lambda ...: seen.setdefault("statement", s) or _RESULT`)으로 쓰면
    setdefault 가 truthy 를 돌려줄 때 `or` 가 단락돼 dict 대신 문자열이 반환된다
    (KeyError: 'efficiency'). 명시 함수로 둔다.
    """
    def _fake(info, statement, code):
        seen["info"] = dict(info)
        seen["statement"] = statement
        seen["code"] = code
        return _RESULT
    return _fake


def test_scrape_failure_never_reaches_the_llm(minimal_client, monkeypatch):
    """수집 실패 문자열이 analyzer 에 도달하면 안 된다 — 빈 본문이어야 한다."""
    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: "크롤링 실패: 404 Client Error: Not Found for url: ...")
    seen = {}
    monkeypatch.setattr(solved_route.analyzer, "analyze_code", _capture(seen))
    _seed_boj()

    resp = minimal_client.post("/api/review-imported/boj/1000")

    assert resp.status_code == 200
    assert seen["statement"] == ""


def test_successful_scrape_reaches_the_llm(minimal_client, monkeypatch):
    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: "【문제】두 정수 A와 B를 입력받아 A+B를 출력한다.")
    seen = {}
    monkeypatch.setattr(solved_route.analyzer, "analyze_code", _capture(seen))
    _seed_boj()

    resp = minimal_client.post("/api/review-imported/boj/1000")

    assert resp.status_code == 200
    assert "A+B를 출력" in seen["statement"]


def test_demo_mode_blocks_the_route(monkeypatch):
    """LLM 을 쓰는 라우터는 전부 데모 가드가 필요하다 — 키가 있으면 방문자가 과금을 발생시킨다."""
    monkeypatch.setattr(solved_route, "IS_DEMO", True)
    monkeypatch.setattr(solved_route.analyzer, "analyze_code",
                        lambda *a, **k: pytest.fail("데모에서 LLM 이 호출되면 안 된다"))
    app = FastAPI()
    app.include_router(solved_route.router)

    resp = TestClient(app).post("/api/review-imported/boj/1000")

    assert resp.status_code == 403


def test_demo_mode_blocks_history_clear(monkeypatch):
    monkeypatch.setattr(solved_route, "IS_DEMO", True)
    _seed_boj()

    app = FastAPI()
    app.include_router(solved_route.router)
    resp = TestClient(app).delete("/api/solved-history")

    assert resp.status_code == 403
    assert db.get_solved_problem("boj", "1000") is not None  # 데모 시드가 지워지면 안 된다


def test_empty_solved_title_does_not_overwrite_resolved_title(minimal_client, monkeypatch):
    """solved 행의 제목이 비어 있으면 문제 조회에서 받은 제목을 살린다.

    CF 전용 경로다 — CF 는 제목·태그를 문제 조회에서 받아오고, BOJ 는 solved 행에서 직접
    채우므로 살릴 다른 출처가 없다."""
    monkeypatch.setattr(solved_route, "resolve_problem_info", lambda *a, **k: {
        "id": 0, "platform": "codeforces", "problem_ref": "4A",
        "title": "Watermelon", "tier": 0, "tier_name": "Codeforces 800", "tags": ["math"],
    })
    monkeypatch.setattr(problem_resolve.api_client, "get_codeforces_problem_statement",
                        lambda ref: "statement body long enough to pass any guard")
    seen = {}
    monkeypatch.setattr(solved_route.analyzer, "analyze_code", _capture(seen))
    db.save_solved_problem(problem_id=0, title="", tier=0, tier_name="Codeforces 800",
                           tags=[], code="print(1)", language="Python 3",
                           platform="codeforces", problem_ref="4A")

    resp = minimal_client.post("/api/review-imported/codeforces/4A")

    assert resp.status_code == 200
    # 응답(=저장된 값)을 본다. seen["info"] 는 analyze_code 호출 시점 스냅샷이라
    # 그 뒤에 있는 가드(routes/solved.py 의 `if problem.get("tags")`)를 검증하지 못한다 —
    # 그 가드를 무조건 대입으로 바꿔도 스냅샷은 그대로다.
    assert resp.json()["title"] == "Watermelon"  # 빈 문자열로 덮이지 않았다
    assert resp.json()["tags"] == ["math"]       # 빈 태그도 덮지 않는다


def test_resolve_problem_info_failure_restores_the_claimed_row(minimal_client, monkeypatch):
    """resolve_problem_info 가 실패해도 선점한 행이 목록에서 사라지면 안 된다."""
    def _raise(*a, **k):
        raise HTTPException(status_code=502, detail="문제 조회 실패")
    monkeypatch.setattr(solved_route, "resolve_problem_info", _raise)
    db.save_solved_problem(problem_id=0, title="Watermelon", tier=0, tier_name="Codeforces 800",
                           tags=["math"], code="print(1)", language="Python 3",
                           platform="codeforces", problem_ref="4A")

    resp = minimal_client.post("/api/review-imported/codeforces/4A")

    assert resp.status_code == 502
    assert db.get_solved_problem("codeforces", "4A") is not None


def test_restored_row_keeps_its_original_imported_at(minimal_client, monkeypatch):
    """되돌린 행은 imported_at 도 원래 값 그대로여야 한다 — 아니면 claim 시각으로
    덮여 목록 순서가 뒤집히고 가져온 날짜가 오늘로 보인다."""
    def _raise(*a, **k):
        raise HTTPException(status_code=502, detail="문제 조회 실패")
    monkeypatch.setattr(solved_route, "resolve_problem_info", _raise)
    db.save_solved_problem(problem_id=0, title="Watermelon", tier=0, tier_name="Codeforces 800",
                           tags=["math"], code="print(1)", language="Python 3",
                           platform="codeforces", problem_ref="4A",
                           imported_at="2026-01-01T00:00:00+00:00")

    resp = minimal_client.post("/api/review-imported/codeforces/4A")

    assert resp.status_code == 502
    restored = db.get_solved_problem("codeforces", "4A")
    assert restored["imported_at"] == "2026-01-01T00:00:00+00:00"
