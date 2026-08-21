"""push_files_to_github 의 기본 브랜치 결정.

GET 으로 알아낸 브랜치를 마지막 PATCH 까지 그대로 쓴다. PATCH 에서 다시 추측하면
두 가지가 걸린다.

1. master 저장소에서 매 push 마다 실패 PATCH 를 1회 낭비한다.
2. 폴백 조건을 특정 상태코드(422)에만 걸면, 없는 ref 에 대한 PATCH 가 404 로 올 때
   raise_for_status() 가 터진다 — 그 시점엔 tree·commit 객체가 이미 만들어져 고아로
   남고, 사용자에게는 "GitHub push에 실패했습니다" 만 보인다.
"""
import pytest

from clients import github

_FILES = [{"path": "1000/1000.py", "content": "print(1)"}]


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"raise_for_status: {self.status_code}")


def _fake_api(default_branch: str, calls: list):
    """default_branch 만 존재하는 저장소를 흉내낸다."""
    def _get(url, **kwargs):
        calls.append(("GET", url))
        if "/git/ref/heads/" in url:
            branch = url.rsplit("/", 1)[1]
            if branch != default_branch:
                return _Resp(404)
            return _Resp(200, {"object": {"sha": "headsha"}})
        return _Resp(200, {"tree": {"sha": "treesha"}})

    def _post(url, **kwargs):
        calls.append(("POST", url))
        return _Resp(201, {"sha": "newsha"})

    def _patch(url, **kwargs):
        calls.append(("PATCH", url))
        branch = url.rsplit("/", 1)[1]
        # 없는 ref 에 대한 PATCH 는 404 다 — 422 만 보는 폴백은 여기서 터진다.
        return _Resp(200 if branch == default_branch else 404)

    return _get, _post, _patch


@pytest.mark.parametrize("default_branch", ["main", "master"])
def test_patch_targets_the_branch_the_get_found(monkeypatch, default_branch):
    calls = []
    get, post, patch = _fake_api(default_branch, calls)
    monkeypatch.setattr(github.requests, "get", get)
    monkeypatch.setattr(github.requests, "post", post)
    monkeypatch.setattr(github.requests, "patch", patch)

    assert github.push_files_to_github("u/r", "tok", _FILES, "msg") is True

    patches = [url for method, url in calls if method == "PATCH"]
    assert len(patches) == 1, f"PATCH 를 {len(patches)}회 보냈다 — 추측이 남아 있다"
    assert patches[0].endswith(f"/git/refs/heads/{default_branch}")


def test_master_repo_does_not_waste_a_failing_patch(monkeypatch):
    calls = []
    get, post, patch = _fake_api("master", calls)
    monkeypatch.setattr(github.requests, "get", get)
    monkeypatch.setattr(github.requests, "post", post)
    monkeypatch.setattr(github.requests, "patch", patch)

    github.push_files_to_github("u/r", "tok", _FILES, "msg")

    assert not any(url.endswith("/git/refs/heads/main") for method, url in calls
                   if method == "PATCH")
