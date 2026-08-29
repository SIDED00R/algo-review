"""/api/execute 의 위임 계약.

운영에서 앱은 코드를 직접 실행하지 않는다 — 격리된 실행 서비스로 넘긴다. "위임한다" 를
반환값으로만 확인하면 앱이 몰래 로컬 실행해도 통과하므로, 로컬 실행 경로를 실패로 심어
배선을 태운다.
"""
import pytest
import requests

from routes import execute as execute_route

_URL = "https://executor.example.run.app"
_REQ = {"code": "print(1)", "language": "Python 3", "stdin": "", "timeout_sec": 5}


class _Response:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def client(minimal_app):
    return minimal_app(execute_route.router)


@pytest.fixture
def delegating(monkeypatch):
    """실행 서비스가 붙은 상태. 로컬 실행 경로는 실패로 막아 둔다."""
    monkeypatch.setattr(execute_route.settings, "executor_url", _URL)
    monkeypatch.setattr(execute_route.settings, "execute_enabled", True)
    monkeypatch.setattr(execute_route, "run_code",
                        lambda *a, **k: pytest.fail("위임 대상이 있으면 앱이 직접 실행하면 안 된다"))
    monkeypatch.setattr(execute_route, "_identity_token", lambda audience: f"tok:{audience}")


def test_request_goes_to_the_executor_with_an_identity_token(monkeypatch, delegating, client):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers, timeout=timeout)
        return _Response(200, {"stdout": "1\n", "stderr": "", "exit_code": 0, "time_ms": 12})

    monkeypatch.setattr(execute_route.requests, "post", fake_post)

    resp = client.post("/api/execute", json=_REQ)

    assert resp.status_code == 200
    assert resp.json() == {"stdout": "1\n", "stderr": "", "exit_code": 0, "time_ms": 12}
    assert sent["url"] == f"{_URL}/run"
    # 토큰의 audience 는 실행 서비스 URL 이어야 한다 — 다른 값이면 실행 서비스가 401 을 준다.
    assert sent["headers"]["Authorization"] == f"Bearer tok:{_URL}"
    assert sent["json"] == {"code": "print(1)", "language": "Python 3",
                            "stdin": "", "timeout_sec": 5}


def test_trailing_slash_in_the_configured_url_does_not_double_up(monkeypatch, delegating, client):
    monkeypatch.setattr(execute_route.settings, "executor_url", _URL + "/")
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["url"] = url
        return _Response(200, {"stdout": "", "stderr": "", "exit_code": 0, "time_ms": 1})

    monkeypatch.setattr(execute_route.requests, "post", fake_post)
    client.post("/api/execute", json=_REQ)

    assert sent["url"] == f"{_URL}/run"


def test_unsupported_language_stays_a_400(monkeypatch, delegating, client):
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: _Response(400, {"detail": "지원하지 않는 언어: Rust"}))

    resp = client.post("/api/execute", json={**_REQ, "language": "Rust"})

    assert resp.status_code == 400
    assert "Rust" in resp.json()["detail"]


def test_executor_failure_becomes_502(monkeypatch, delegating, client):
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: _Response(500, text="boom"))

    resp = client.post("/api/execute", json=_REQ)

    assert resp.status_code == 502
    # 실행 서비스의 응답 본문을 그대로 내보내지 않는다.
    assert "boom" not in resp.json()["detail"]


def test_unreachable_executor_becomes_502(monkeypatch, delegating, client):
    def fake_post(*a, **k):
        raise requests.ConnectionError(f"failed to connect to {_URL} with Bearer tok")

    monkeypatch.setattr(execute_route.requests, "post", fake_post)

    resp = client.post("/api/execute", json=_REQ)

    assert resp.status_code == 502
    # 예외 원문에는 URL·토큰이 실린다 — 응답에 새면 안 된다.
    assert "Bearer" not in resp.json()["detail"]
    assert _URL not in resp.json()["detail"]


def test_demo_blocks_before_delegating(monkeypatch, delegating, client):
    monkeypatch.setattr(execute_route, "IS_DEMO", True)
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: pytest.fail("데모에서 실행 서비스를 부르면 안 된다"))

    assert client.post("/api/execute", json=_REQ).status_code == 403


def test_repeated_calls_from_one_ip_are_throttled(monkeypatch, delegating, client):
    """인증이 없는 엔드포인트라 한 IP 가 실행 서비스를 독점하지 못하게 막는다."""
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: _Response(200, {"stdout": "", "stderr": "",
                                                        "exit_code": 0, "time_ms": 1}))

    for _ in range(execute_route._RATE_LIMIT_PER_MINUTE):
        assert client.post("/api/execute", json=_REQ).status_code == 200

    assert client.post("/api/execute", json=_REQ).status_code == 429


def test_throttling_counts_the_forwarded_client_not_the_proxy(monkeypatch, delegating, client):
    """Cloud Run 뒤에서는 request.client 가 GFE 다 — 그걸 세면 전 사용자가 한 버킷이 된다."""
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: _Response(200, {"stdout": "", "stderr": "",
                                                        "exit_code": 0, "time_ms": 1}))
    noisy = {"x-forwarded-for": "203.0.113.7, 130.211.0.1"}

    for _ in range(execute_route._RATE_LIMIT_PER_MINUTE):
        assert client.post("/api/execute", json=_REQ, headers=noisy).status_code == 200

    assert client.post("/api/execute", json=_REQ, headers=noisy).status_code == 429
    # 다른 IP 는 영향을 받지 않아야 한다.
    other = {"x-forwarded-for": "198.51.100.4"}
    assert client.post("/api/execute", json=_REQ, headers=other).status_code == 200


def test_global_limit_holds_even_when_the_forwarded_ip_rotates_every_request(monkeypatch, delegating, client):
    """XFF 를 매번 새 값으로 바꿔도(위조) 전역 상한은 토폴로지와 무관하게 걸린다."""
    monkeypatch.setattr(execute_route.requests, "post",
                        lambda *a, **k: _Response(200, {"stdout": "", "stderr": "",
                                                        "exit_code": 0, "time_ms": 1}))

    for i in range(execute_route._GLOBAL_LIMIT):
        headers = {"x-forwarded-for": f"5.5.5.{i}"}
        assert client.post("/api/execute", json=_REQ, headers=headers).status_code == 200

    headers = {"x-forwarded-for": f"5.5.5.{execute_route._GLOBAL_LIMIT}"}
    assert client.post("/api/execute", json=_REQ, headers=headers).status_code == 429


def test_recent_calls_stays_capped_even_with_unbounded_forged_keys(monkeypatch):
    """요청자가 정하는 키(XFF)로 무한히 자라지 않는다 — 상한을 넘으면 가장 오래된 것부터 버려진다.

    전역 한도를 끈 상태에서만 이 분기에 닿는다.
    """
    monkeypatch.setattr(execute_route, "_recent_calls", {})
    monkeypatch.setattr(execute_route, "_global_calls", [])
    # 이 테스트는 버킷 수 상한만 본다 — 전역 상한은 다른 테스트가 이미 검증했다.
    monkeypatch.setattr(execute_route, "_GLOBAL_LIMIT", 10 ** 9)

    for i in range(execute_route._MAX_BUCKETS + 500):
        execute_route._enforce_rate_limit(f"forged-{i}")

    assert len(execute_route._recent_calls) <= execute_route._MAX_BUCKETS
