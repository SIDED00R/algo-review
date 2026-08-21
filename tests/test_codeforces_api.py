"""CF API 응답 파싱 — comment 우선 처리 및 자격증명 비노출 회귀 (네트워크 불필요)."""
from urllib.parse import urlencode

import pytest
import requests

from clients import codeforces


class _FakeResponse:
    def __init__(self, params):
        self.status_code = 400
        self._params = params

    def json(self):
        return {"status": "FAILED", "comment": "handle: User with handle nope not found"}

    def raise_for_status(self):
        # 실제 requests.HTTPError 메시지엔 서명된 요청 URL(apiKey/apiSig 포함)이 그대로 들어간다 —
        # 이 경로를 타면 안 된다는 걸 확인하려고 일부러 여기 담아둔다.
        raise requests.exceptions.HTTPError(
            f"400 Client Error: Bad Request for url: .../user.info?{urlencode(self._params)}"
        )


def test_api_request_surfaces_cf_comment_without_leaking_credentials(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(params)

    monkeypatch.setattr(codeforces.requests, "get", fake_get)

    with pytest.raises(ValueError) as exc_info:
        codeforces._codeforces_api_request(
            "user.info", {"handles": "nope"}, api_key="AK", api_secret="ASECRET",
        )

    message = str(exc_info.value)
    assert message == "handle: User with handle nope not found"
    assert "AK" not in message  # apiKey 값이 메시지에 새지 않는다
    assert captured["params"].get("apiSig")  # 실제로는 서명돼 있었다 — raise_for_status를 탔다면 샜을 것


def test_signed_request_error_never_leaks_the_api_signature(monkeypatch):
    """서명된 요청의 쿼리스트링에는 apiKey·apiSig 가 들어 있다.

    requests 의 HTTPError 메시지는 요청 URL 전문을 포함하므로 raise_for_status() 를 그대로
    쓰면 안 된다 — 그 예외는 routes/import_codeforces.py 의 `except Exception as e` 를 타고
    500 detail 로 클라이언트에게 반환되고 로그에도 남는다. 서버에 CODEFORCES_API_KEY 가
    설정된 배포에서는 요청자가 키를 넣지 않아도 운영자 키+유효 서명이 노출된다.
    """
    class _Resp:
        status_code = 502
        ok = False
        url = ("https://codeforces.com/api/user.status"
               "?apiKey=SECRETKEY123&apiSig=abc123DEADBEEF&handle=x")

        def json(self):
            raise ValueError("not json")   # CF 가 HTML 오류 페이지를 준 경우

        def raise_for_status(self):
            raise requests.HTTPError(f"502 Server Error: for url: {self.url}")

    # 형제 테스트와 같이 monkeypatch 를 쓴다 — 수동 save/restore 는 실패 시 원복이 새기 쉽다.
    monkeypatch.setattr(codeforces.requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(ValueError) as exc:
        codeforces._codeforces_api_request("user.status", {"handle": "x"},
                                           api_key="SECRETKEY123", api_secret="SECRET456")
    message = str(exc.value)

    assert "SECRETKEY123" not in message
    assert "DEADBEEF" not in message
    assert "apiSig" not in message
    assert "502" in message   # 상태코드는 남긴다
