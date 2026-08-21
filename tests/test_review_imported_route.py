"""/api/review-imported 회귀.

가져온 기록 AI 리뷰는 리뷰·재리뷰와 **같은 해석기**로 문제 본문을 얻어야 한다.
예전에는 수집 함수를 직접 불러, 실패 시 반환되는 문자열(`"크롤링 실패: 404 …"`)이 그대로
LLM 프롬프트의 문제 설명 자리에 박혔다 — acmicpc.net 종료 이후 BOJ 는 상시 그 상태였고
결과가 DB 에 영구 저장됐다.
"""
import pytest
from fastapi import FastAPI
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
def client(monkeypatch):
    monkeypatch.setattr(solved_route, "IS_DEMO", False)
    monkeypatch.setattr(solved_route.settings, "openai_api_key", "sk-test")
    app = FastAPI()
    app.include_router(solved_route.router)
    return TestClient(app)


def _seed_boj():
    db.save_solved_problem(**_SOLVED_BOJ)


def _capture(seen):
    """analyze_code 대역. setdefault 의 반환값을 그대로 쓰면 truthy 일 때 결과가 뒤바뀐다."""
    def _fake(info, statement, code):
        seen["info"] = dict(info)
        seen["statement"] = statement
        seen["code"] = code
        return _RESULT
    return _fake


def test_scrape_failure_never_reaches_the_llm(client, monkeypatch):
    """수집 실패 문자열이 analyzer 에 도달하면 안 된다 — 빈 본문이어야 한다."""
    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: "크롤링 실패: 404 Client Error: Not Found for url: ...")
    seen = {}
    monkeypatch.setattr(solved_route.analyzer, "analyze_code", _capture(seen))
    _seed_boj()

    resp = client.post("/api/review-imported/boj/1000")

    assert resp.status_code == 200
    assert seen["statement"] == ""


def test_successful_scrape_reaches_the_llm(client, monkeypatch):
    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: "【문제】두 정수 A와 B를 입력받아 A+B를 출력한다.")
    seen = {}
    monkeypatch.setattr(solved_route.analyzer, "analyze_code", _capture(seen))
    _seed_boj()

    resp = client.post("/api/review-imported/boj/1000")

    assert resp.status_code == 200
    assert "A+B를 출력" in seen["statement"]


def test_demo_mode_blocks_the_route(monkeypatch):
    """LLM 을 쓰는 라우터 중 이것만 데모 가드가 없었다 — 키가 있으면 방문자가 과금을 발생시킨다."""
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


def test_empty_solved_title_does_not_overwrite_resolved_title(client, monkeypatch):
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

    resp = client.post("/api/review-imported/codeforces/4A")

    assert resp.status_code == 200
    # 응답(=저장된 값)을 본다. seen["info"] 는 analyze_code 호출 시점 스냅샷이라
    # 그 뒤에 있는 가드(routes/solved.py 의 `if problem.get("tags")`)를 검증하지 못한다 —
    # 무조건 대입으로 바꿔도 스냅샷은 그대로여서 거짓 초록이었다.
    assert resp.json()["title"] == "Watermelon"  # 빈 문자열로 덮이지 않았다
    assert resp.json()["tags"] == ["math"]       # 빈 태그도 덮지 않는다
