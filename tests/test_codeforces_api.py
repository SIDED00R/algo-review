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
