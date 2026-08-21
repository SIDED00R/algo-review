"""Codeforces 자격증명이 예외 메시지로 새어 나가지 않는지.

`_codeforces_api_request` 는 서명 호출에서 apiKey·apiSig 를 **쿼리스트링**에 넣는다.
requests 계열 예외 메시지는 요청 URL 전문을 포함하므로, 그 예외가 그대로 라우터의
`detail=f"...: {e}"` 를 타면 **인증 없는 공개 엔드포인트**(/api/import-codeforces)가
운영자 키와 유효 서명을 익명 요청자에게 반환한다.

raise_for_status() 는 이미 막고 있었지만 `requests.get` 자체가 던지는
ConnectTimeout·ConnectionError 는 막혀 있지 않았다(urllib3 MaxRetryError 를 감싸며
"Max retries exceeded with url: /api/user.status?...&apiKey=..." 를 남긴다).
"""
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from clients import codeforces
from routes import import_codeforces

_KEY = "SECRETKEY123"
_SIG_SECRET = "SIGSECRET456"


def _raiser(exc):
    def _get(*args, **kwargs):
        # requests 가 실제로 만드는 메시지 형태를 그대로 흉내낸다 — URL 전문이 들어간다.
        url = kwargs.get("params", {})
        raise exc(f"HTTPSConnectionPool(host='codeforces.com', port=443): "
                  f"Max retries exceeded with url: /api/user.status?"
                  f"apiKey={url.get('apiKey')}&apiSig={url.get('apiSig')}")
    return _get


@pytest.mark.parametrize("exc", [requests.ConnectTimeout, requests.ConnectionError,
                                 requests.ReadTimeout, requests.TooManyRedirects])
def test_transport_errors_never_carry_the_query_string(monkeypatch, exc):
    monkeypatch.setattr(codeforces.requests, "get", _raiser(exc))

    with pytest.raises(ValueError) as caught:
        codeforces._codeforces_api_request(
            "user.status", {"handle": "x"}, api_key=_KEY, api_secret=_SIG_SECRET)

    message = str(caught.value)
    assert _KEY not in message
    assert "apiSig" not in message
    assert "Max retries" not in message
    assert exc.__name__ in message, "무슨 실패였는지는 남아야 한다"


def test_signed_request_actually_puts_the_key_in_the_query(monkeypatch):
    """위 테스트가 무엇을 지키는지 고정한다 — 키가 쿼리에 없다면 검사가 무의미해진다."""
    seen = {}

    def _get(url, params=None, **kwargs):
        seen.update(params or {})
        raise requests.ConnectTimeout("boom")

    monkeypatch.setattr(codeforces.requests, "get", _get)
    with pytest.raises(ValueError):
        codeforces._codeforces_api_request(
            "user.status", {"handle": "x"}, api_key=_KEY, api_secret=_SIG_SECRET)

    assert seen["apiKey"] == _KEY
    # apiSig = rand(6자리) + sha512 hex(128자)
    assert len(seen["apiSig"]) == 6 + 128


def test_route_does_not_echo_unknown_exception_text(monkeypatch):
    """라우터의 500 detail 도 예외 원문을 그대로 싣지 않는다(2중 방어)."""
    def _boom(*a, **k):
        raise RuntimeError(f"apiKey={_KEY} leaked through an unexpected path")

    monkeypatch.setattr(import_codeforces.api_client, "get_codeforces_user_info", _boom)
    monkeypatch.setattr(import_codeforces, "IS_DEMO", False)

    app = FastAPI()
    app.include_router(import_codeforces.router)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/api/import-codeforces", json={"handle": "tourist"})

    assert r.status_code == 500
    assert _KEY not in r.text
    assert "RuntimeError" in r.json()["detail"]
