from db.connection import session_scope
from db.models import GithubSetting


def get_github_settings() -> dict | None:
    with session_scope() as session:
        obj = session.get(GithubSetting, 1)
        if obj is None or not obj.access_token:
            return None
        return {
            "access_token": obj.access_token,
            "github_username": obj.github_username,
            "target_repo": obj.target_repo,
        }


def save_github_settings(access_token: str, github_username: str, target_repo: str = ""):
    with session_scope(commit=True) as session:
        obj = session.get(GithubSetting, 1)
        if obj is None:
            session.add(GithubSetting(
                id=1,
                access_token=access_token,
                github_username=github_username,
                target_repo=target_repo,
            ))
            return
        obj.access_token = access_token
        obj.github_username = github_username
        # target_repo 가 빈 문자열이면 기존 값을 보존한다.
        if target_repo != "":
            obj.target_repo = target_repo


def update_github_target_repo(target_repo: str):
    with session_scope(commit=True) as session:
        obj = session.get(GithubSetting, 1)
        if obj is not None:
            obj.target_repo = target_repo


def delete_github_settings():
    with session_scope(commit=True) as session:
        obj = session.get(GithubSetting, 1)
        if obj is not None:
            session.delete(obj)
