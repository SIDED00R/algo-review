"""수집 함수의 실패 문자열과 그 판별자가 함께 움직이는지.

본문 수집 함수(`get_problem_statement` · `get_codeforces_problem_statement`)는 예외 대신
**실패 문자열**을 돌려준다. `routes.problem_resolve.is_scrape_failure` 가 접두사로 그걸
가려내지 못하면, 그 문자열이 LLM 프롬프트의 문제 설명 자리에 그대로 박히고
`save_review` 가 `problem_statement` 로 영구 저장한다.

여기서는 `requests` 만 스텁하고 **실제 생산자**를 호출한다.
"""
from unittest.mock import MagicMock, patch

import pytest

import clients as api_client
from clients import codeforces, solved_ac
from routes.problem_resolve import is_scrape_failure


def _html(body: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.status_code = 200
    resp.text = body
    resp.content = body.encode("utf-8")
    return resp


def test_boj_request_failure_is_recognised():
    """요청 자체가 실패하는 경로 — acmicpc.net 종료로 상시 이 상태다."""
    with patch.object(solved_ac.requests, "get", side_effect=RuntimeError("blocked")):
        result = api_client.get_problem_statement(1000)
    assert is_scrape_failure(result), f"판별자가 놓친 실패 문자열: {result!r}"


def test_boj_page_without_sections_is_recognised():
    """200 인데 문제 섹션이 없는 경로 — 점검 페이지·리다이렉트."""
    with patch.object(solved_ac.requests, "get", lambda *a, **k: _html("<html><body></body></html>")):
        result = api_client.get_problem_statement(1000)
    assert is_scrape_failure(result), f"판별자가 놓친 실패 문자열: {result!r}"


def test_codeforces_scrape_failure_is_recognised():
    with patch.object(codeforces.requests, "get", side_effect=RuntimeError("blocked")):
        result = api_client.get_codeforces_problem_statement("4A")
    assert is_scrape_failure(result), f"판별자가 놓친 실패 문자열: {result!r}"


def test_a_real_statement_is_not_mistaken_for_a_failure():
    """정상 본문을 실패로 보면 반대 방향으로 조용히 망가진다 — 본문 없이 리뷰가 나간다."""
    page = ('<html><body><div id="problem_description"><p>두 정수를 더하시오.</p></div>'
            '<div id="problem_input"><p>첫 줄에 A 와 B.</p></div></body></html>')
    with patch.object(solved_ac.requests, "get", lambda *a, **k: _html(page)):
        result = api_client.get_problem_statement(1000)
    assert result.strip()
    assert not is_scrape_failure(result), f"정상 본문을 실패로 봤다: {result[:60]!r}"


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_text_counts_as_a_failure(text):
    assert is_scrape_failure(text)
