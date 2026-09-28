"""로그인 게이트 — 세션 쿠키 서명·만료·허용 목록, 미로그인 요청 차단, 예외 경로, 데모·설정 누락."""
import pytest

import login_gate
from login_gate import SESSION_COOKIE, make_session, session_email

_EMAIL = "me@gmail.com"


@pytest.fixture
def login_on(monkeypatch):
    monkeypatch.setattr(login_gate.settings, "google_client_id", "cid")
    monkeypatch.setattr(login_gate.settings, "google_client_secret", "secret")
    monkeypatch.setattr(login_gate.settings, "auth_allowed_emails", f" {_EMAIL.upper()} , other@gmail.com")
    monkeypatch.setattr(login_gate.settings, "app_url", "https://app.example")


def test_session_round_trip(login_on):
    assert session_email(make_session(_EMAIL)) == _EMAIL


def test_session_rejects_tampering_and_garbage(login_on):
    good = make_session(_EMAIL)
    encoded, expires, signature = good.split(".")
    forged_expiry = f"{encoded}.{int(expires) + 999}.{signature}"
    assert session_email(forged_expiry) is None
    assert session_email(good[:-1] + ("0" if good[-1] != "0" else "1")) is None
    for garbage in ("", "a.b", "a.b.c.d", "메일.1.서명", good + "."):
        assert session_email(garbage) is None


def test_session_expires(login_on, monkeypatch):
    session = make_session(_EMAIL)
    monkeypatch.setattr(login_gate.time, "time", lambda: 10**12)
    assert session_email(session) is None


def test_session_is_revoked_by_the_allow_list_and_the_secret(login_on, monkeypatch):
    session = make_session(_EMAIL)
    monkeypatch.setattr(login_gate.settings, "auth_allowed_emails", "other@gmail.com")
    assert session_email(session) is None
    monkeypatch.setattr(login_gate.settings, "auth_allowed_emails", _EMAIL)
    monkeypatch.setattr(login_gate.settings, "google_client_secret", "rotated")
    assert session_email(session) is None


def _no_redirect(client):
    client.follow_redirects = False
    return client


def test_signed_out_shell_goes_to_login_and_apis_are_401(client, login_on):
    c = _no_redirect(client)
    r = c.get("/")
    # 요청이 들어온 호스트가 아니라 APP_URL 로 보낸다(콜백이 APP_URL 로 오므로 state 쿠키도 그 호스트에).
    assert r.status_code == 307 and r.headers["location"] == "https://app.example/auth/google"
    r = c.get("/api/stats?platform=boj")
    assert r.status_code == 401
    assert "로그인" in r.json()["detail"]


def test_public_paths_pass_without_login(client, login_on):
    c = _no_redirect(client)
    assert c.get("/health").status_code == 200
    assert c.get("/static/js/utils.js").status_code == 200
    # 배포 워크플로가 무인증으로 예제 실행을 확인한다 — 게이트가 아니라 라우트가 답해야 한다.
    r = c.post("/api/execute", json={"code": "print(1)", "language": "Python 3", "stdin": "", "timeout_sec": 5})
    assert r.status_code != 401


def test_signed_in_request_reaches_the_app(client, login_on):
    c = _no_redirect(client)
    c.cookies.set(SESSION_COOKIE, make_session(_EMAIL))
    r = c.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_demo_needs_no_login(client, login_on, monkeypatch):
    monkeypatch.setattr(login_gate, "IS_DEMO", True)
    assert _no_redirect(client).get("/").status_code == 200


def test_cloud_run_without_login_settings_fails_closed(client, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "algo-review")
    c = _no_redirect(client)
    r = c.get("/api/stats?platform=boj")
    assert r.status_code == 503
    assert "GOOGLE_CLIENT_ID" in r.json()["detail"]
    assert c.get("/health").status_code == 200


def test_cloud_run_needs_an_https_app_url(client, login_on, monkeypatch):
    """기본값(http://localhost:8080)이 남으면 콜백이 localhost 로 가 아무도 로그인하지 못한다 — 먼저 막는다."""
    monkeypatch.setenv("K_SERVICE", "algo-review")
    monkeypatch.setattr(login_gate.settings, "app_url", "http://localhost:8080")
    c = _no_redirect(client)
    r = c.get("/")
    assert r.status_code == 503 and "APP_URL" in r.json()["detail"]
    c.cookies.set(SESSION_COOKIE, make_session(_EMAIL))
    assert c.get("/api/stats?platform=boj").status_code == 503   # 세션이 있어도 막힌다
    assert c.get("/health").status_code == 200


def test_cloud_run_with_an_https_app_url_serves_signed_in_requests(client, login_on, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "algo-review")
    c = _no_redirect(client)
    c.cookies.set(SESSION_COOKIE, make_session(_EMAIL))
    assert c.get("/").status_code == 200


def test_local_http_app_url_still_logs_in(client, login_on, monkeypatch):
    monkeypatch.setattr(login_gate.settings, "app_url", "http://localhost:8080")
    r = _no_redirect(client).get("/")
    assert r.status_code == 307 and r.headers["location"] == "http://localhost:8080/auth/google"


def test_local_without_login_settings_stays_open(client):
    assert _no_redirect(client).get("/").status_code == 200
