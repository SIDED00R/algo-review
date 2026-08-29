"""GitHub OAuth 콜백은 실패해도 500 이 아니라 리다이렉트여야 한다.

compare_digest 는 non-ASCII str 에 TypeError 를 던진다 — state 는 요청 쿼리에서 오는
임의 문자열이라 그대로 넣으면 500 이 샌다. 이 경로의 정상 실패는 리다이렉트다.
"""
import pytest

from routes import auth


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(auth, "IS_DEMO", False)
    return minimal_app(auth.router)


def test_non_ascii_state_signature_redirects_instead_of_500(minimal_client):
    nonce = "abc123"
    state = f"{nonce}.9999999999.시그니처"

    resp = minimal_client.get(
        "/auth/github/callback",
        params={"code": "x", "state": state},
        cookies={"oauth_nonce": nonce},
        follow_redirects=False,
    )

    assert resp.status_code == 307
    assert "github=error" in resp.headers["location"]
