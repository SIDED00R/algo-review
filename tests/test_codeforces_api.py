"""CF API 응답 파싱 — comment 우선 처리와 자격증명 비노출 (네트워크 불필요)."""
from urllib.parse import urlencode

import pytest
import requests

from clients import codeforces
from clients.utils import UpstreamUnavailable


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
    assert captured["params"].get("apiSig")  # 쿼리에 서명이 실린다 — 예외 원문이 새면 함께 나간다


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


class _MappedResponse:
    """상태코드와 본문만 정한 CF 응답. 실제 requests.Response 와 같은 속성만 노출한다."""

    def __init__(self, status, body):
        self.status_code = status
        self.ok = 200 <= status < 400
        self._body = body

    def json(self):
        if self._body is _NO_JSON:
            raise ValueError("not json")
        return self._body


_NO_JSON = object()
_LIMIT = {"status": "FAILED", "comment": "Call limit exceeded"}

# CF 가 실제로 주는 응답 형태 → 라우터가 매핑할 예외.
# UpstreamUnavailable = 502(상류 장애), 그 외 ValueError = 400(요청자 입력 오류).
_MAPPING = [
    (503, _LIMIT,                                        UpstreamUnavailable),
    (429, _LIMIT,                                        UpstreamUnavailable),
    (500, {"status": "FAILED", "comment": "boom"},        UpstreamUnavailable),
    (503, _NO_JSON,                                       UpstreamUnavailable),
    (403, _NO_JSON,                                       UpstreamUnavailable),   # Cloudflare 차단
    (200, _NO_JSON,                                       UpstreamUnavailable),   # 점검 페이지
    (200, [1, 2, 3],                                      UpstreamUnavailable),   # dict 가 아닌 JSON
    (200, {"status": "OK"},                               UpstreamUnavailable),   # result 누락
    (400, {"status": "FAILED", "comment": "handle: bad"},  ValueError),
    (404, {"status": "FAILED"},                            ValueError),
]


@pytest.mark.parametrize("status,body,expected", _MAPPING,
                         ids=[f"{s}-{e.__name__}" for s, _, e in _MAPPING])
def test_response_shape_maps_to_the_right_exception(monkeypatch, status, body, expected):
    """상태코드를 comment 보다 먼저 본다.

    CF 는 레이트리밋·점검 응답에도 `comment` 를 실어 준다. comment 유무로 먼저 갈라내면
    5xx·429 가 400 으로 보고되어, 사용자는 자기 입력을 고치려 하고 상류 장애는 알림에
    잡히지 않는다.
    """
    monkeypatch.setattr(codeforces.requests, "get",
                        lambda *a, **k: _MappedResponse(status, body))
    with pytest.raises(expected) as caught:
        codeforces._codeforces_api_request("problemset.problems")
    if expected is ValueError:
        assert not isinstance(caught.value, UpstreamUnavailable)


def test_no_exception_escapes_as_something_other_than_value_error(monkeypatch):
    """이 함수를 나가는 예외는 전부 ValueError 계열이다.

    쿼리스트링에 apiKey·apiSig 가 실리므로, 다른 타입이 새면 그 메시지가 라우터의
    `except Exception` 을 타고 그대로 응답에 담길 수 있다.
    """
    for status, body in [(200, {"status": "OK"}), (200, {}), (200, [1]), (200, "text"),
                         (500, _NO_JSON), (400, {"status": "FAILED"})]:
        monkeypatch.setattr(codeforces.requests, "get",
                            lambda *a, **k: _MappedResponse(status, body))
        with pytest.raises(ValueError):
            codeforces._codeforces_api_request("problemset.problems")
