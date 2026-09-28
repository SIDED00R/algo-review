"""구글 로그인(OAuth 2.0 인가 코드 흐름) — 인가 URL 조립과 코드 → ID 토큰 클레임 교환."""
import base64
import json
import time
from urllib.parse import urlencode

import requests

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def google_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """이메일만 받는 인가 URL. prompt=select_account 로 매번 계정을 고르게 한다."""
    return _AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    })


def _jwt_claims(id_token: str) -> dict:
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def exchange_google_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """인가 코드를 ID 토큰으로 바꿔 클레임을 돌려준다. 발급자·대상·만료가 맞지 않으면 ValueError.

    ID 토큰의 서명은 검증하지 않는다 — 구글 토큰 엔드포인트에서 TLS 로 직접 받은 토큰이다
    (OpenID Connect Core 3.1.3.7). 브라우저를 거쳐 온 토큰에는 이 함수를 쓰면 안 된다.
    """
    resp = requests.post(_TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=10)
    resp.raise_for_status()
    id_token = resp.json().get("id_token") or ""
    if not id_token:
        raise ValueError("구글 응답에 ID 토큰이 없습니다.")
    claims = _jwt_claims(id_token)
    if claims.get("iss") not in _ISSUERS or claims.get("aud") != client_id:
        raise ValueError("ID 토큰의 발급자 또는 대상이 맞지 않습니다.")
    if int(claims.get("exp", 0)) < time.time():
        raise ValueError("만료된 ID 토큰입니다.")
    return claims
