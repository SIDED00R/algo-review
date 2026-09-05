"""상류 장애의 상태코드와 응답 본문.

두 가지를 함께 고정한다.

1. **상태코드** — 상류 장애는 502 다. 연결 실패를 입력 형식 오류와 같은 타입으로 두면
   라우터가 400 으로 매핑하고, 사용자는 "Codeforces API 연결 실패 (ConnectTimeout)" 를
   400 과 함께 보고 **자기 입력을 고치려 한다**.
2. **본문** — openai SDK 의 `APIStatusError` 메시지는 `Error code: 401 - {제공자 응답
   본문}` 형태로 제공자 본문을 그대로 싣는다. `.env.example` 이 OpenAI 호환 서드파티
   엔드포인트를 1급 대안으로 안내하므로 그 본문 형태를 통제할 수 없고, `base_url` 이
   내부 프록시면 그 주소도 함께 나간다.
"""
import httpx
import openai
import pytest
import requests
from openai._base_client import BaseClient

import db
from clients import UpstreamUnavailable, codeforces
from config import settings
from routes import problem_resolve, report, review, solved

_SECRET_BODY = {"error": {"message": "Invalid key sk-SECRET123 at https://internal-proxy.corp"}}


def _openai_error() -> Exception:
    """SDK 가 실제로 만드는 예외 — 메시지에 제공자 응답 본문이 통째로 들어간다."""
    req = httpx.Request("POST", "https://internal-proxy.corp/v1/chat/completions")
    resp = httpx.Response(401, json=_SECRET_BODY, request=req)
    resp.read()
    client = openai.OpenAI(api_key="k", base_url="https://internal-proxy.corp/v1")
    return BaseClient._make_status_error_from_response(client, resp)


def test_the_sdk_really_puts_the_provider_body_in_the_message():
    """이 테스트가 무엇을 지키는지 고정한다 — 전제가 깨지면 나머지 검사가 무의미해진다."""
    assert "sk-SECRET123" in str(_openai_error())


@pytest.mark.parametrize("exc", [requests.ConnectTimeout, requests.ConnectionError])
def test_codeforces_transport_error_is_upstream_unavailable(monkeypatch, exc):
    monkeypatch.setattr(codeforces.requests, "get", lambda *a, **k: (_ for _ in ()).throw(exc("x")))
    with pytest.raises(UpstreamUnavailable):
        codeforces._codeforces_api_request("problemset.problems")


def test_upstream_unavailable_is_still_a_value_error():
    """UpstreamUnavailable 은 ValueError 를 상속한다. 기존 `except ValueError` 핸들러가 그대로 동작한다."""
    assert issubclass(UpstreamUnavailable, ValueError)


def test_cf_problem_lookup_failure_maps_to_502(monkeypatch):
    """상류 장애는 502 다 — 400 은 사용자가 자기 입력을 고치려 하게 만든다."""
    from fastapi import HTTPException

    def _boom(_ref):
        raise UpstreamUnavailable("Codeforces API 연결 실패 (ConnectTimeout)")

    monkeypatch.setattr(problem_resolve.api_client, "get_codeforces_problem_info", _boom)
    with pytest.raises(HTTPException) as caught:
        problem_resolve.resolve_problem_info("codeforces", None, "4A")
    assert caught.value.status_code == 502


def test_bad_ref_is_still_400(monkeypatch):
    """상류 장애만 502 로 옮긴다 — 진짜 입력 오류는 400 그대로여야 한다."""
    from fastapi import HTTPException

    def _boom(_ref):
        raise ValueError("Codeforces 문제를 찾을 수 없습니다: 9999Z")

    monkeypatch.setattr(problem_resolve.api_client, "get_codeforces_problem_info", _boom)
    with pytest.raises(HTTPException) as caught:
        problem_resolve.resolve_problem_info("codeforces", None, "9999Z")
    assert caught.value.status_code == 400


_REVIEW_BODY = {"platform": "boj", "problem_id": 1000,
                "code": "print(1)", "language": "Python 3"}


def test_review_does_not_echo_the_provider_body(monkeypatch, minimal_app):
    monkeypatch.setattr(review, "IS_DEMO", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(review, "resolve_problem_info", lambda *a, **k: {
        "id": 1000, "platform": "boj", "problem_ref": "1000", "title": "A+B",
        "tier": 1, "tier_name": "Bronze V", "tags": []})
    monkeypatch.setattr(review, "resolve_statement", lambda *a, **k: "")
    monkeypatch.setattr(review.analyzer, "analyze_code",
                        lambda *a, **k: (_ for _ in ()).throw(_openai_error()))

    r = minimal_app(review.router).post("/api/review", json=_REVIEW_BODY)

    assert r.status_code == 502
    assert "sk-SECRET123" not in r.text
    assert "internal-proxy" not in r.text
    assert "AuthenticationError" in r.json()["detail"], "무슨 실패였는지는 남아야 한다"


def test_analyzer_user_message_still_reaches_the_user(monkeypatch, minimal_app):
    """원문 차단이 사용자용 안내까지 삼키면 안 된다 — analyzer 가 직접 만든 ValueError 는 통과."""
    monkeypatch.setattr(review, "IS_DEMO", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(review, "resolve_problem_info", lambda *a, **k: {
        "id": 1000, "platform": "boj", "problem_ref": "1000", "title": "A+B",
        "tier": 1, "tier_name": "Bronze V", "tags": []})
    monkeypatch.setattr(review, "resolve_statement", lambda *a, **k: "")
    monkeypatch.setattr(review.analyzer, "analyze_code", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("AI 가 빈 응답을 돌려줬습니다. 잠시 후 다시 시도해주세요.")))

    r = minimal_app(review.router).post("/api/review", json=_REVIEW_BODY)

    assert r.status_code == 502
    assert "빈 응답" in r.json()["detail"]


def test_report_does_not_echo_the_provider_body(monkeypatch, minimal_app):
    db.save_review(problem_id=1000, title="A+B", tier=1, tags=["math"], code="print(1)",
                   feedback="f", efficiency="good", platform="boj", problem_ref="1000",
                   tier_name="Bronze V")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(report.analyzer, "get_cumulative_analysis",
                        lambda *a, **k: (_ for _ in ()).throw(_openai_error()))

    r = minimal_app(report.router).get("/api/report?platform=boj")

    assert r.status_code == 502
    assert "sk-SECRET123" not in r.text


def test_review_imported_does_not_echo_the_provider_body(monkeypatch, minimal_app):
    db.save_solved_problem(problem_id=1000, title="A+B", tier=1, tier_name="Bronze V",
                           tags=["math"], code="print(1)", language="Python 3",
                           platform="boj", problem_ref="1000")
    monkeypatch.setattr(solved, "IS_DEMO", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(solved, "resolve_statement", lambda *a, **k: "")
    monkeypatch.setattr(solved.analyzer, "analyze_code",
                        lambda *a, **k: (_ for _ in ()).throw(_openai_error()))

    r = minimal_app(solved.router).post("/api/review-imported/boj/1000")

    assert r.status_code == 502
    assert "sk-SECRET123" not in r.text


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_codeforces_server_side_failures_are_upstream(monkeypatch, status):
    """HTTP 응답을 받았어도 5xx·429 는 CF 쪽 문제다 — 요청자가 입력을 고쳐도 달라지지 않는다."""
    class _Resp:
        status_code = status
        ok = False

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(codeforces.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(UpstreamUnavailable):
        codeforces._codeforces_api_request("problemset.problems")


def test_codeforces_client_side_failure_stays_a_value_error(monkeypatch):
    """comment 없는 4xx 는 요청 문제로 본다 — 400 이 맞다."""
    class _Resp:
        status_code = 400
        ok = False

        def json(self):
            return {"status": "FAILED"}

    monkeypatch.setattr(codeforces.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ValueError) as caught:
        codeforces._codeforces_api_request("problemset.problems")
    assert not isinstance(caught.value, UpstreamUnavailable)


def test_run_llm_lets_an_httpexception_through():
    """호출부가 만든 4xx 를 run_llm 이 삼키면 입력 오류가 상류 장애(502)로 뒤바뀐다."""
    from fastapi import HTTPException

    from routes.helpers import run_llm

    def boom():
        raise HTTPException(status_code=400, detail="저장된 코드가 없습니다.")

    with pytest.raises(HTTPException) as caught:
        run_llm("코드 분석 실패", boom)
    assert caught.value.status_code == 400
    assert caught.value.detail == "저장된 코드가 없습니다."
