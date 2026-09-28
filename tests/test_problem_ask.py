"""문제 뷰어 질문 — 프롬프트 조립, Claude 우선·OpenAI 호환 폴백, 라우트 검증·데모."""
import pytest

import problem_tutor
from constants import PLATFORMS
from routes import problem_ask


class _FakeCompletions:
    def __init__(self, content, finish_reason="stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("_Message", (), {"content": self.content})()
        choice = type("_Choice", (), {"finish_reason": self.finish_reason, "message": message})()
        return type("_Response", (), {"choices": [choice]})()


def _fake_client(content, finish_reason="stop"):
    completions = _FakeCompletions(content, finish_reason)
    return type("_Client", (), {"chat": type("_Chat", (), {"completions": completions})}), completions


def _openai_must_not_run():
    raise AssertionError("OpenAI 호환 경로를 타면 안 된다")


def test_prompt_carries_the_problem_code_history_and_question():
    prompt = problem_tutor.build_user_prompt(
        "codeforces", "4A", "Watermelon", "### 문제\n수박을 나눈다", "힌트만 주세요",
        code="print(1)", history=[{"question": "입력 범위는?", "answer": "1 이상 100 이하"}])
    assert "- 플랫폼: Codeforces" in prompt
    assert "- 문제 식별자: 4A" in prompt
    assert "수박을 나눈다" in prompt
    assert "## 사용자 코드\n```\nprint(1)\n```" in prompt
    assert prompt.index("입력 범위는?") < prompt.index("1 이상 100 이하") < prompt.index("## 이번 질문")
    assert prompt.endswith("## 이번 질문\n힌트만 주세요")


def test_prompt_omits_the_code_section_without_code_and_marks_a_missing_statement():
    prompt = problem_tutor.build_user_prompt("leetcode", "two-sum", "Two Sum", "  ", "질문")
    assert "## 사용자 코드" not in prompt
    assert "본문 없음" in prompt
    assert "## 앞선 질문" not in prompt


def test_claude_answer_is_used_and_labelled(monkeypatch):
    monkeypatch.setattr(problem_tutor, "claude_answer", lambda s, u: "Claude 답")
    monkeypatch.setattr(problem_tutor, "get_client", _openai_must_not_run)
    assert problem_tutor.answer_question("boj", "1000", "A+B", "", "질문") == ("Claude 답", "Claude")


def test_fallback_answers_with_the_configured_model(monkeypatch):
    client, completions = _fake_client("Gemini 답")
    monkeypatch.setattr(problem_tutor, "claude_answer", lambda s, u: None)
    monkeypatch.setattr(problem_tutor, "get_client", lambda: client)
    monkeypatch.setattr(problem_tutor.settings, "openai_model", "gemini-test")
    assert problem_tutor.answer_question("boj", "1000", "A+B", "", "질문") == ("Gemini 답", "gemini-test")
    assert completions.calls[0]["model"] == "gemini-test"
    assert completions.calls[0]["messages"][0]["role"] == "system"


def test_fallback_marks_a_truncated_answer(monkeypatch):
    client, _ = _fake_client("길게 쓰다 잘린", "length")
    monkeypatch.setattr(problem_tutor, "claude_answer", lambda s, u: None)
    monkeypatch.setattr(problem_tutor, "get_client", lambda: client)
    answer, _ = problem_tutor.answer_question("boj", "1000", "A+B", "", "질문")
    assert answer.startswith("길게 쓰다 잘린") and "잘렸습니다" in answer


def test_fallback_empty_answer_is_a_readable_error(monkeypatch):
    client, _ = _fake_client("   ")
    monkeypatch.setattr(problem_tutor, "claude_answer", lambda s, u: None)
    monkeypatch.setattr(problem_tutor, "get_client", lambda: client)
    with pytest.raises(ValueError, match="빈 응답"):
        problem_tutor.answer_question("boj", "1000", "A+B", "", "질문")


_BODY = {"platform": "codeforces", "problem_ref": "4A", "title": "Watermelon",
         "statement": "본문", "question": "  힌트만 주세요  ", "code": "print(1)",
         "history": [{"question": "q1", "answer": "a1"}]}


@pytest.fixture
def ask_client(minimal_app, monkeypatch):
    monkeypatch.setattr(problem_ask, "require_openai_key", lambda *a, **k: None)
    return minimal_app(problem_ask.router)


def test_route_passes_the_request_through_and_returns_the_model(ask_client, monkeypatch):
    seen = []
    monkeypatch.setattr(problem_ask.problem_tutor, "answer_question",
                        lambda *args: seen.append(args) or ("답", "Claude"))
    r = ask_client.post("/api/problem/ask", json=_BODY)
    assert r.status_code == 200, r.text
    assert r.json() == {"answer": "답", "model": "Claude"}
    assert seen == [("codeforces", "4A", "Watermelon", "본문", "힌트만 주세요", "print(1)",
                     [{"question": "q1", "answer": "a1"}])]


@pytest.mark.parametrize("override", [
    {"question": "   "},
    {"platform": "atcoder"},
    {"history": [{"question": "q", "answer": "a"}] * 6},
    {"problem_ref": ""},
])
def test_route_rejects_invalid_requests_before_the_llm(ask_client, monkeypatch, override):
    monkeypatch.setattr(problem_ask.problem_tutor, "answer_question",
                        lambda *args: (_ for _ in ()).throw(AssertionError("LLM 을 부르면 안 된다")))
    r = ask_client.post("/api/problem/ask", json={**_BODY, **override})
    assert r.status_code == 422


def test_route_maps_a_readable_llm_error_to_502(ask_client, monkeypatch):
    def _fail(*args):
        raise ValueError("AI 가 빈 응답을 돌려줬습니다. 잠시 후 다시 시도해주세요.")

    monkeypatch.setattr(problem_ask.problem_tutor, "answer_question", _fail)
    r = ask_client.post("/api/problem/ask", json=_BODY)
    assert r.status_code == 502
    assert "빈 응답" in r.json()["detail"]


@pytest.mark.parametrize("platform", PLATFORMS)
def test_demo_answers_every_platform_without_the_llm(minimal_app, monkeypatch, platform):
    monkeypatch.setattr(problem_ask, "IS_DEMO", True)
    monkeypatch.setattr(problem_ask.problem_tutor, "answer_question",
                        lambda *args: (_ for _ in ()).throw(AssertionError("LLM 을 부르면 안 된다")))
    r = minimal_app(problem_ask.router).post("/api/problem/ask", json={**_BODY, "platform": platform})
    assert r.status_code == 200
    assert r.json()["model"] == "데모"
    # 데모 뷰어가 보여주는 문제(CF Watermelon·LeetCode Two Sum)에 맞는 답이어야 한다.
    answer = r.json()["answer"]
    if platform == "codeforces":
        assert "$w$" in answer
    elif platform == "leetcode":
        assert "$w$" not in answer and "해시맵" in answer
