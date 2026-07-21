"""db.github_settings 파사드의 현행 동작 고정."""
import db


def test_save_and_get_roundtrip():
    db.save_github_settings("tok", "user", "owner/repo")
    got = db.get_github_settings()
    assert got["access_token"] == "tok"
    assert got["github_username"] == "user"
    assert got["target_repo"] == "owner/repo"


def test_empty_target_repo_preserves_existing():
    db.save_github_settings("tok", "user", "owner/repo")
    db.save_github_settings("tok2", "user2", "")
    got = db.get_github_settings()
    assert got["access_token"] == "tok2"
    assert got["github_username"] == "user2"
    # target_repo 를 빈 문자열로 저장해도 기존 값이 보존된다(CASE WHEN).
    assert got["target_repo"] == "owner/repo"


def test_empty_access_token_reads_as_none():
    db.save_github_settings("", "user", "owner/repo")
    assert db.get_github_settings() is None


def test_get_when_absent_returns_none():
    assert db.get_github_settings() is None
