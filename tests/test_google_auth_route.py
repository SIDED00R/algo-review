"""구글 로그인 흐름 — 인가 URL·state 쿠키, 콜백 검증(state·이메일 인증·허용 목록), ID 토큰 클레임 검사."""
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

import login_gate
from clients import google_oauth
from login_gate import SESSION_COOKIE, session_email
from routes import google_auth

# 13바이트 — base64 로 바꾸면 패딩(=)이 붙는 길이라 쿠키 값의 따옴표 여부를 가린다.
_EMAIL = "you@gmail.com"


@pytest.fixture
def login_on(monkeypatch):
    monkeypatch.setattr(login_gate.settings, "google_client_id", "cid")
    monkeypatch.setattr(login_gate.settings, "google_client_secret", "secret")
    monkeypatch.setattr(login_gate.settings, "auth_allowed_emails", _EMAIL)
    monkeypatch.setattr(login_gate.settings, "app_url", "https://app.example")


@pytest.fixture
def auth_client(minimal_app):
    return minimal_app(google_auth.router, follow_redirects=False)


def test_start_redirects_to_google_with_a_matching_state_cookie(auth_client, login_on):
    r = auth_client.get("/auth/google")
    assert r.status_code == 307
    url = urlparse(r.headers["location"])
    query = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["https://app.example/auth/google/callback"]
    assert query["scope"] == ["openid email"]
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"google_oauth_state={query['state'][0]};")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" in cookie


def test_start_without_settings_is_503(auth_client):
    assert auth_client.get("/auth/google").status_code == 503


@pytest.mark.parametrize("path", ["/auth/google", "/auth/google/callback"])
def test_cloud_run_login_flow_needs_an_https_app_url(auth_client, login_on, monkeypatch, path):
    monkeypatch.setenv("K_SERVICE", "algo-review")
    monkeypatch.setattr(login_gate.settings, "app_url", "http://localhost:8080")
    r = auth_client.get(path)
    assert r.status_code == 503 and "APP_URL" in r.text


def _callback(client, *, cookie_state="s1", state="s1", code="c"):
    if cookie_state is not None:
        client.cookies.set("google_oauth_state", cookie_state)
    return client.get("/auth/google/callback", params={"code": code, "state": state})


@pytest.mark.parametrize("cookie_state, state", [(None, "s1"), ("s1", "s2"), ("s1", "상태")])
def test_callback_rejects_a_missing_or_mismatched_state(auth_client, login_on, monkeypatch, cookie_state, state):
    monkeypatch.setattr(google_auth.api_client, "exchange_google_code",
                        lambda *a: (_ for _ in ()).throw(AssertionError("교환하면 안 된다")))
    r = _callback(auth_client, cookie_state=cookie_state, state=state)
    assert r.status_code == 400
    assert SESSION_COOKIE not in r.headers.get("set-cookie", "")


@pytest.mark.parametrize("raw_cookie", ['google_oauth_state="\\351"', 'google_oauth_state="\\354\\203\\201"'])
def test_callback_rejects_a_non_ascii_state_cookie(auth_client, login_on, raw_cookie):
    """쿠키는 8진 이스케이프로 비ASCII 가 된다 — compare_digest 의 TypeError 가 500 으로 새면 안 된다."""
    r = auth_client.get("/auth/google/callback", params={"code": "c", "state": "s1"},
                        headers={"cookie": raw_cookie})
    assert r.status_code == 400


def test_callback_signs_in_an_allowed_verified_email(auth_client, login_on, monkeypatch):
    seen = []
    monkeypatch.setattr(google_auth.api_client, "exchange_google_code",
                        lambda *a: seen.append(a) or {"email": "You@Gmail.com", "email_verified": True})
    r = _callback(auth_client)
    assert r.status_code == 307 and r.headers["location"] == "/"
    assert seen == [("c", "cid", "secret", "https://app.example/auth/google/callback")]
    session = r.cookies.get(SESSION_COOKIE)
    assert session_email(session) == _EMAIL
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith(f"{SESSION_COOKIE}="))
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" in cookie
    assert cookie.startswith(f"{SESSION_COOKIE}={session};")   # 따옴표로 감싸지지 않은 값 그대로


@pytest.mark.parametrize("claims", [
    {"email": "stranger@gmail.com", "email_verified": True},
    {"email": _EMAIL, "email_verified": False},
    {"email": _EMAIL},
])
def test_callback_refuses_other_or_unverified_accounts(auth_client, login_on, monkeypatch, claims):
    monkeypatch.setattr(google_auth.api_client, "exchange_google_code", lambda *a: claims)
    r = _callback(auth_client)
    assert r.status_code == 403
    assert SESSION_COOKIE not in r.headers.get("set-cookie", "")


def test_callback_reports_a_failed_exchange(auth_client, login_on, monkeypatch):
    def _fail(*a):
        raise ValueError("ID 토큰의 발급자 또는 대상이 맞지 않습니다.")

    monkeypatch.setattr(google_auth.api_client, "exchange_google_code", _fail)
    assert _callback(auth_client).status_code == 502


def test_demo_skips_login(auth_client, login_on, monkeypatch):
    monkeypatch.setattr(google_auth, "IS_DEMO", True)
    for path in ("/auth/google", "/auth/google/callback"):
        r = auth_client.get(path)
        assert r.status_code == 307 and r.headers["location"] == "/"


def _id_token(claims: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def _fake_token_endpoint(monkeypatch, claims, seen=None):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id_token": _id_token(claims)} if claims is not None else {}

    def _post(url, data, timeout):
        if seen is not None:
            seen.append((url, data))
        return _Resp()

    monkeypatch.setattr(google_oauth.requests, "post", _post)


_GOOD = {"iss": "https://accounts.google.com", "aud": "cid", "exp": time.time() + 600,
         "email": _EMAIL, "email_verified": True}


def test_exchange_returns_the_id_token_claims(monkeypatch):
    seen = []
    _fake_token_endpoint(monkeypatch, _GOOD, seen)
    claims = google_oauth.exchange_google_code("code", "cid", "sec", "https://app/cb")
    assert claims["email"] == _EMAIL
    url, data = seen[0]
    assert url == "https://oauth2.googleapis.com/token"
    assert data["grant_type"] == "authorization_code" and data["redirect_uri"] == "https://app/cb"


@pytest.mark.parametrize("override", [{"aud": "other"}, {"iss": "https://evil.example"}, {"exp": 1}])
def test_exchange_rejects_foreign_or_expired_tokens(monkeypatch, override):
    _fake_token_endpoint(monkeypatch, {**_GOOD, **override})
    with pytest.raises(ValueError):
        google_oauth.exchange_google_code("code", "cid", "sec", "https://app/cb")


def test_exchange_without_an_id_token_raises(monkeypatch):
    _fake_token_endpoint(monkeypatch, None)
    with pytest.raises(ValueError, match="ID 토큰이 없습니다"):
        google_oauth.exchange_google_code("code", "cid", "sec", "https://app/cb")
