"""LeetCode 리뷰 경로 — 요청이 저장 행까지 배선되고, SQL 언어면 SQL 프롬프트를 쓴다."""
import json

import analyzer
import db
from routes import problem_resolve, review

_INFO = {
    "id": 175, "platform": "leetcode", "problem_ref": "combine-two-tables", "title": "Combine Two Tables",
    "tier": 1, "tier_name": "LeetCode Easy", "tags": ["Database"],
    "url": "https://leetcode.com/problems/combine-two-tables/",
}
_RESULT = {"efficiency": "ok", "complexity": "Person 전체 스캔 1회", "better_algorithm": None,
           "feedback": "f", "strengths": [], "weaknesses": []}
_JSON_KEYS = ("efficiency", "complexity", "better_algorithm", "feedback", "strengths", "weaknesses")


def test_leetcode_review_resolves_by_number_and_saves_the_slug(minimal_app, monkeypatch):
    seen = {}

    def _info(ref):
        seen["ref"] = ref
        return dict(_INFO)

    def _analyze(info, statement, code, language=""):
        seen["language"] = language
        seen["platform"] = info["platform"]
        return dict(_RESULT)

    monkeypatch.setattr(review, "require_openai_key", lambda *a, **k: None)
    monkeypatch.setattr(problem_resolve.api_client, "get_leetcode_problem_info", _info)
    monkeypatch.setattr(review, "resolve_statement", lambda *a, **k: "본문")
    monkeypatch.setattr(review.analyzer, "analyze_code", _analyze)

    r = minimal_app(review.router).post("/api/review", json={
        "platform": "leetcode", "problem_ref": "175", "code": "SELECT 1 FROM t", "language": "MySQL"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["platform"], body["problem_ref"], body["problem_id"], body["tier"], body["tier_name"]) == \
        ("leetcode", "combine-two-tables", 175, 1, "LeetCode Easy")
    assert body["problem_url"] == "https://leetcode.com/problems/combine-two-tables/"
    assert seen == {"ref": "175", "language": "MySQL", "platform": "leetcode"}

    rows = db.get_reviews_by_problem("leetcode", "combine-two-tables")
    assert rows and rows[0]["problem_id"] == 175 and rows[0]["tier_name"] == "LeetCode Easy"
    assert rows[0]["language"] == "MySQL"


def test_missing_ref_is_400_before_any_lookup(minimal_app, monkeypatch):
    monkeypatch.setattr(review, "require_openai_key", lambda *a, **k: None)
    monkeypatch.setattr(problem_resolve.api_client, "get_leetcode_problem_info",
                        lambda ref: (_ for _ in ()).throw(AssertionError("조회하면 안 된다")))
    r = minimal_app(review.router).post("/api/review", json={
        "platform": "leetcode", "code": "x", "language": "Python 3"})
    assert r.status_code == 400
    assert "LeetCode" in r.json()["detail"]


def test_sql_language_switches_the_prompt_but_keeps_the_json_keys():
    system_sql, user_sql = analyzer.build_review_prompts(_INFO, "본문", "SELECT 1", "MySQL")
    system_algo, user_algo = analyzer.build_review_prompts(_INFO, "본문", "print(1)", "Python 3")
    assert "SQL 쿼리 리뷰" in system_sql
    assert "알고리즘 코드 리뷰" in system_algo
    assert "```sql\nSELECT 1" in user_sql
    assert "```python\nprint(1)" in user_algo
    assert "플랫폼: LeetCode" in user_sql
    for prompt in (user_sql, user_algo):
        for key in _JSON_KEYS:
            assert f'"{key}"' in prompt, f"{key} 가 프롬프트의 JSON 형식에 없다"
    assert analyzer.is_sql_language("postgresql")
    assert analyzer.is_sql_language("MS SQL Server")
    assert not analyzer.is_sql_language("Python 3")


def test_analyze_code_sends_the_sql_prompt_for_sql_language(monkeypatch):
    captured = {}

    class _Completions:
        @staticmethod
        def create(**kwargs):
            captured["messages"] = kwargs["messages"]
            message = type("_Message", (), {"content": json.dumps(_RESULT)})()
            choice = type("_Choice", (), {"finish_reason": "stop", "message": message})()
            return type("_Response", (), {"choices": [choice]})()

    client = type("_Client", (), {"chat": type("_Chat", (), {"completions": _Completions})})
    monkeypatch.setattr(analyzer, "get_client", lambda: client)

    result = analyzer.analyze_code(_INFO, "본문", "SELECT 1", language="MySQL")
    assert "SQL 쿼리 리뷰" in captured["messages"][0]["content"]
    assert result["better_algorithm"] == ""   # null 은 저장 가능한 빈 문자열로

    analyzer.analyze_code(_INFO, "본문", "print(1)", language="Python 3")
    assert "알고리즘 코드 리뷰" in captured["messages"][0]["content"]
