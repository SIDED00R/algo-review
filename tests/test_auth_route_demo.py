"""데모 모드에서 GitHub 설정 변경·연결 해제가 실제 DB 를 건드리면 안 된다."""
import pytest

import db
from routes import auth


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(auth, "IS_DEMO", True)
    return minimal_app(auth.router)


def test_demo_mode_blocks_repo_change(minimal_client):
    db.save_github_settings(access_token="tok", github_username="me", target_repo="me/old")

    r = minimal_client.post("/auth/github/repo", json={"repo": "me/new"})

    assert r.status_code == 403
    assert db.get_github_settings()["target_repo"] == "me/old"


def test_demo_mode_blocks_disconnect(minimal_client):
    db.save_github_settings(access_token="tok", github_username="me", target_repo="me/old")

    r = minimal_client.delete("/auth/github")

    assert r.status_code == 403
    assert db.get_github_settings() is not None
