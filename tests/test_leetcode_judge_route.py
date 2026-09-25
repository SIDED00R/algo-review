"""/api/leetcode/run · /api/leetcode/submit — 채점기 클라이언트를 대역으로 두고 해석·오류 매핑·상한을 본다."""
import clients as api_client
from clients import ProblemNotFound
from clients.leetcode_judge import LeetCodeRateLimited, LeetCodeSessionError
from routes import leetcode_judge as route

_RAW = {"question_id": "1", "title": "Two Sum"}


def _client(minimal_app, monkeypatch):
    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: dict(_RAW))
    route._recent_calls.clear()
    return minimal_app(route.router)


def test_run_resolves_slug_and_forwards_cases(minimal_app, monkeypatch):
    seen = {}

    def _run(slug, question_id, language, code, cases):
        seen.update(slug=slug, question_id=question_id, language=language, code=code, cases=cases)
        return {"status_msg": "Accepted", "run_success": True, "runtime": "0 ms", "error": "", "cases": []}

    monkeypatch.setattr(route, "run_examples", _run)
    client = _client(minimal_app, monkeypatch)
    r = client.post("/api/leetcode/run", json={"problem_ref": "https://leetcode.com/problems/Two-Sum/",
                                               "language": "cpp", "code": "int x;", "cases": ["[2,7]\n9"]})
    assert r.status_code == 200, r.text
    assert seen == {"slug": "two-sum", "question_id": "1", "language": "cpp", "code": "int x;", "cases": ["[2,7]\n9"]}


def test_submit_forwards_and_returns_judge_result(minimal_app, monkeypatch):
    monkeypatch.setattr(route, "submit_solution",
                        lambda slug, qid, lang, code: {"submission_id": "7", "accepted": True,
                                                       "status_msg": "Accepted"})
    client = _client(minimal_app, monkeypatch)
    r = client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "language": "mysql", "code": "select 1"})
    assert r.status_code == 200 and r.json()["accepted"] is True


def test_error_mapping(minimal_app, monkeypatch):
    client = _client(minimal_app, monkeypatch)
    assert client.post("/api/leetcode/run",
                       json={"problem_ref": "two-sum", "code": "x", "cases": []}).status_code == 400
    assert client.post("/api/leetcode/run", json={"problem_ref": "two-sum", "language": "java", "code": "x",
                                                  "cases": ["1"]}).status_code == 400
    assert client.post("/api/leetcode/submit", json={"problem_ref": "Bad Slug!", "code": "x"}).status_code == 400

    monkeypatch.setattr(route, "submit_solution",
                        lambda *a: (_ for _ in ()).throw(LeetCodeSessionError("세션 만료")))
    r = client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "code": "x"})
    assert (r.status_code, r.json()["detail"]) == (401, "세션 만료")

    monkeypatch.setattr(route, "submit_solution", lambda *a: (_ for _ in ()).throw(LeetCodeRateLimited("제한")))
    assert client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "code": "x"}).status_code == 429

    monkeypatch.setattr(route, "submit_solution", lambda *a: (_ for _ in ()).throw(KeyError("interpret_id")))
    r = client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "code": "x"})
    assert r.status_code == 502 and "KeyError" in r.json()["detail"] and "interpret_id" not in r.json()["detail"]

    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: (_ for _ in ()).throw(ProblemNotFound("없음")))
    assert client.post("/api/leetcode/submit", json={"problem_ref": "nope", "code": "x"}).status_code == 404


def test_demo_blocks_and_global_rate_limit(minimal_app, monkeypatch):
    client = _client(minimal_app, monkeypatch)
    monkeypatch.setattr(route, "IS_DEMO", True)
    assert client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "code": "x"}).status_code == 403
    monkeypatch.setattr(route, "IS_DEMO", False)

    monkeypatch.setattr(route, "_GLOBAL_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(route, "submit_solution", lambda *a: {"accepted": True})
    codes = [client.post("/api/leetcode/submit", json={"problem_ref": "two-sum", "code": "x"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
