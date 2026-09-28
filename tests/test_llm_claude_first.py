"""리뷰·리포트·번역이 Claude 답을 먼저 쓰고, 답이 없거나 못 읽으면 OpenAI 호환 경로로 가는지."""
import json

import pytest

import analyzer
import statement_translator

_INFO = {"id": 1000, "platform": "boj", "problem_ref": "1000", "title": "A+B",
         "tier": 1, "tier_name": "Bronze V", "tags": ["수학"]}
_RESULT = {"efficiency": "good", "complexity": "O(1)", "better_algorithm": None,
           "feedback": "f", "strengths": ["s"], "weaknesses": []}


def _openai_must_not_run():
    raise AssertionError("OpenAI 호환 경로를 타면 안 된다")


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        message = type("_Message", (), {"content": self.content})()
        choice = type("_Choice", (), {"finish_reason": "stop", "message": message})()
        return type("_Response", (), {"choices": [choice]})()


def _fake_client(content):
    completions = _FakeCompletions(content)
    return type("_Client", (), {"chat": type("_Chat", (), {"completions": completions})}), completions


def test_review_uses_the_fenced_claude_json(monkeypatch):
    monkeypatch.setattr(analyzer, "claude_answer",
                        lambda s, u: "```json\n" + json.dumps(_RESULT, ensure_ascii=False) + "\n```")
    monkeypatch.setattr(analyzer, "get_client", _openai_must_not_run)
    result = analyzer.analyze_code(_INFO, "본문", "print(1)", "Python 3")
    assert result["efficiency"] == "good"
    assert result["better_algorithm"] == ""   # 정규화도 Claude 답에 그대로 적용된다


@pytest.mark.parametrize("claude_raw", ["JSON 이 아닌 설명문", "[]", "null", '"문자열"'])
def test_review_falls_back_when_claude_answer_is_not_a_json_object(monkeypatch, claude_raw):
    client, completions = _fake_client(json.dumps(_RESULT))
    monkeypatch.setattr(analyzer, "claude_answer", lambda s, u: claude_raw)
    monkeypatch.setattr(analyzer, "get_client", lambda: client)
    assert analyzer.analyze_code(_INFO, "본문", "print(1)", "Python 3")["complexity"] == "O(1)"
    assert completions.calls == 1


def test_review_falls_back_when_claude_has_no_answer(monkeypatch):
    client, completions = _fake_client(json.dumps(_RESULT))
    monkeypatch.setattr(analyzer, "claude_answer", lambda s, u: None)
    monkeypatch.setattr(analyzer, "get_client", lambda: client)
    analyzer.analyze_code(_INFO, "본문", "print(1)", "Python 3")
    assert completions.calls == 1


def test_report_returns_the_claude_text(monkeypatch):
    prompts = []
    monkeypatch.setattr(analyzer, "claude_answer", lambda s, u: prompts.append(u) or "리포트 본문")
    monkeypatch.setattr(analyzer, "get_client", _openai_must_not_run)
    stats = [{"tag": "dp", "total_count": 2, "good_count": 1, "poor_count": 1}]
    assert analyzer.get_cumulative_analysis(stats, []) == "리포트 본문"
    assert "dp: 총 2회" in prompts[0]


def test_translation_unmasks_image_markers_in_the_claude_text(monkeypatch):
    url = "https://espresso.codeforces.com/a7487d7e62f90136b78ae3fbf0a008396f146e13.png"
    sent = []
    monkeypatch.setattr(statement_translator, "claude_answer",
                        lambda s, u: sent.append(u) or "확률은 ⟦img:0⟧ 이다")
    monkeypatch.setattr(statement_translator, "get_client", _openai_must_not_run)
    out = statement_translator.translate_statement(f"probability is ⟦img:{url}⟧", "t", source="Codeforces")
    assert out == f"확률은 ⟦img:{url}⟧ 이다"
    assert "⟦img:0⟧" in sent[0] and url not in sent[0]   # Claude 에도 마스킹된 본문만 간다
