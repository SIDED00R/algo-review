"""재리뷰 라우트 — 외부 API·LLM 을 타지 않는 경로만 검증한다.

test_routes_smoke.py 와 같은 이유로 대상 라우터만 얹은 최소 앱을 쓴다(server.py lifespan 회피).
GitHub 설정 테이블이 비어 있으므로 push 는 항상 pushed=false 로 떨어진다.
"""
import pytest

import db
from routes import problem_resolve, rereview


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app(rereview.router)


def _save(efficiency, **kw):
    args = {
        "problem_id": 1000, "title": "A+B", "tier": 1, "tags": ["구현"],
        "code": "print(1)", "feedback": "", "efficiency": efficiency,
        "problem_ref": "1000", "language": "Python 3",
    }
    args.update(kw)
    db.save_review(**args)


def test_rejects_unknown_platform(minimal_client):
    assert minimal_client.post("/api/rereview/leetcode/1000").status_code == 400


def test_missing_record_returns_404(minimal_client):
    assert minimal_client.post("/api/rereview/boj/1000").status_code == 404


def test_reviewed_row_skips_llm_and_reports_push_failure(minimal_client, monkeypatch):
    _save("good", feedback="f")
    monkeypatch.setattr(rereview.analyzer, "analyze_code",
                        lambda *a, **k: pytest.fail("이미 리뷰된 행에서 LLM 을 호출하면 안 된다"))

    body = minimal_client.post("/api/rereview/boj/1000").json()
    assert body["reviewed"] is False
    assert body["pushed"] is False  # GitHub 미연결
    assert "GitHub" in body["detail"]


def test_pending_row_is_filled_by_review(minimal_client, monkeypatch):
    _save(db.PENDING_EFFICIENCY)
    monkeypatch.setattr(rereview.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(rereview, "resolve_statement", lambda *a, **k: "문제 본문")
    monkeypatch.setattr(rereview.analyzer, "analyze_code", lambda *a, **k: {
        "efficiency": "ok", "complexity": "O(N)", "better_algorithm": None,
        "feedback": "피드백", "strengths": [], "weaknesses": [],
    })

    body = minimal_client.post("/api/rereview/boj/1000").json()
    assert body["reviewed"] is True
    saved = db.get_reviews_by_problem("boj", "1000")
    assert len(saved) == 1  # 회차가 늘지 않는다
    assert saved[0]["efficiency"] == "ok"
    assert saved[0]["complexity"] == "O(N)"


def test_pending_row_without_api_key_returns_500(minimal_client, monkeypatch):
    """설정 누락은 서버 문제다 — review·report·solved 와 같은 500 을 쓴다."""
    _save(db.PENDING_EFFICIENCY)
    monkeypatch.setattr(rereview.settings, "openai_api_key", "")

    r = minimal_client.post("/api/rereview/boj/1000")
    assert r.status_code == 500
    # 리뷰는 여전히 대기 상태로 남는다 — 나중에 다시 시도할 수 있다.
    assert db.get_reviews_by_problem("boj", "1000")[0]["efficiency"] == db.PENDING_EFFICIENCY


def test_stored_statement_reaches_the_llm(minimal_client, monkeypatch):
    """저장된 본문이 있으면 LLM 프롬프트에 그것이 들어가고 스크래핑을 타지 않는다.

    resolve_statement 를 통째로 patch 하면 인자 전달 여부를 검증할 수 없다 — 수집 함수를
    pytest.fail 로 두어 "스크래핑을 타지 않았다"를 실제로 고정한다. README push 와 LLM
    호출이 같은 저장값을 써야 한다(한쪽만 쓰면 백필한 본문이 버려진다).
    """
    stored = "【문제】 두 정수 A와 B를 입력받아 A+B를 출력한다."
    _save(db.PENDING_EFFICIENCY, problem_statement=stored)
    monkeypatch.setattr(rereview.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: pytest.fail("저장된 본문이 있으면 스크래핑하면 안 된다"))
    seen = {}

    def fake_analyze(info, statement, code):
        seen["statement"] = statement
        return {"efficiency": "ok", "complexity": "O(N)", "better_algorithm": None,
                "feedback": "피드백", "strengths": [], "weaknesses": []}

    monkeypatch.setattr(rereview.analyzer, "analyze_code", fake_analyze)

    body = minimal_client.post("/api/rereview/boj/1000").json()

    assert body["reviewed"] is True
    assert seen["statement"] == stored


def test_repush_passes_stored_statement_as_description(minimal_client, monkeypatch):
    """저장된 본문을 넘기면 push_review_bundle 이 스크래핑을 건너뛴다.

    BOJ 는 acmicpc.net 종료로 스크래핑이 빈 섹션을 돌려주고, 그대로 README 를 재생성하면
    이미 올라가 있던 문제 설명을 지운다.
    """
    stored = "【문제】\n두 정수 A와 B를 입력받아 A+B를 출력한다."
    _save("good", feedback="f", problem_statement=stored)
    monkeypatch.setattr(rereview, "merged_github_target", lambda: ("me/solutions", "tok"))

    seen = {}

    def fake_push(repo, token, **kw):
        seen.update(kw)
        return "백준/Bronze/1000번. A+B"

    monkeypatch.setattr(rereview, "push_review_bundle", fake_push)
    body = minimal_client.post("/api/rereview/boj/1000").json()

    assert body["pushed"] is True
    assert seen["description"] == stored
