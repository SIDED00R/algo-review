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


def test_repush_falls_back_to_an_earlier_round_statement(minimal_client, monkeypatch, at_time):
    """최신 회차에 본문이 없으면 이전 회차의 본문을 버리지 않고 그대로 재푸시한다."""
    stored = "【문제】\n두 정수 A와 B를 입력받아 A+B를 출력한다."
    at_time("2026-01-01T00:00:00")
    _save("good", feedback="f", problem_statement=stored)
    at_time("2026-01-02T00:00:00")
    _save("good", feedback="f2", problem_statement="")
    monkeypatch.setattr(rereview, "merged_github_target", lambda: ("me/solutions", "tok"))

    seen = {}

    def fake_push(repo, token, **kw):
        seen.update(kw)
        return "백준/Bronze/1000번. A+B"

    monkeypatch.setattr(rereview, "push_review_bundle", fake_push)
    body = minimal_client.post("/api/rereview/boj/1000").json()

    assert body["pushed"] is True
    assert seen["description"] == stored


def test_llm_result_lands_on_the_round_that_was_reviewed(minimal_client, monkeypatch, at_time):
    """LLM 이 도는 사이에 대기 회차가 하나 더 쌓여도 결과는 리뷰한 회차에 붙어야 한다.

    사용자는 재리뷰를 눌러 두고(10~20초) 메인 탭에서 같은 문제를 '리뷰 없이 올리기' 로
    다시 등록할 수 있다. "최신 대기 행" 에 쓰면 **리뷰한 적 없는 코드**가 리뷰 결과를
    갖게 되고, 그 조합이 그대로 GitHub README 로 올라간다.
    """
    at_time("2026-01-01T00:00:00")
    _save(db.PENDING_EFFICIENCY, code="코드 A")
    monkeypatch.setattr(rereview.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(rereview, "resolve_statement", lambda *a, **k: "문제 본문")

    pushed_code = {}

    def _fake_analyze(problem_info, statement, code):
        # LLM 호출 중에 사용자가 같은 문제를 다시 대기 등록한다.
        at_time("2026-01-02T00:00:00")
        _save(db.PENDING_EFFICIENCY, code="코드 B")
        return {"efficiency": "poor", "complexity": "O(N^2)", "better_algorithm": "",
                "feedback": f"리뷰 대상: {code}", "strengths": [], "weaknesses": []}

    def _fake_push(platform, problem_ref, review):
        pushed_code["code"] = review["code"]
        return True, None

    monkeypatch.setattr(rereview.analyzer, "analyze_code", _fake_analyze)
    monkeypatch.setattr(rereview, "_repush_bundle", _fake_push)

    body = minimal_client.post("/api/rereview/boj/1000").json()
    assert body["reviewed"] is True

    rounds = {r["code"]: r for r in db.get_reviews_by_problem("boj", "1000")}
    assert rounds["코드 A"]["feedback"] == "리뷰 대상: 코드 A"
    assert rounds["코드 A"]["efficiency"] == "poor"
    # 리뷰한 적 없는 회차는 대기 상태 그대로여야 한다.
    assert rounds["코드 B"]["efficiency"] == db.PENDING_EFFICIENCY
    # README 에도 리뷰한 그 회차의 코드가 올라가야 한다.
    assert pushed_code["code"] == "코드 A"


def test_a_round_filled_meanwhile_is_reported_as_conflict(minimal_client, monkeypatch, at_time):
    """LLM 이 도는 사이 그 회차가 이미 채워졌으면 덮어쓰지 않고 409 로 알린다."""
    at_time("2026-01-01T00:00:00")
    _save(db.PENDING_EFFICIENCY, code="코드 A")
    target = db.get_reviews_by_problem("boj", "1000")[0]["id"]
    monkeypatch.setattr(rereview.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(rereview, "resolve_statement", lambda *a, **k: "문제 본문")

    def _fake_analyze(problem_info, statement, code):
        db.update_pending_review("boj", "1000", {
            "efficiency": "good", "complexity": "O(N)", "better_algorithm": "",
            "feedback": "먼저 도착한 리뷰", "strengths": [], "weaknesses": [],
        }, review_id=target)
        return {"efficiency": "poor", "complexity": "", "better_algorithm": "",
                "feedback": "뒤늦게 도착한 리뷰", "strengths": [], "weaknesses": []}

    monkeypatch.setattr(rereview.analyzer, "analyze_code", _fake_analyze)

    r = minimal_client.post("/api/rereview/boj/1000")
    assert r.status_code == 409
    row = db.get_reviews_by_problem("boj", "1000")[0]
    assert row["feedback"] == "먼저 도착한 리뷰"
