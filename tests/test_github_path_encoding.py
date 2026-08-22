"""GitHub API 로 나가는 저장소 경로가 URL 로 인코딩되는지.

폴더명에 문제 제목이 그대로 들어간다(`routes.helpers.build_solution_target`). 제목의
`?` 는 쿼리 구분자, `#` 는 프래그먼트 구분자라, 인코딩하지 않으면 요청이 **잘린 경로**로
나간다. `push_solution` 은 README 와 코드를 각각 PUT 하므로 둘이 같은 잘린 경로를
가리키고 뒤에 올라간 것이 앞을 덮어쓴다 — 그런데 GitHub 는 양쪽 모두 2xx 를 주기 때문에
호출부는 성공으로 집계하고 로그도 남지 않는다.
"""
from unittest.mock import MagicMock, patch

import pytest

from clients import github as gh
from routes.helpers import build_solution_target

_TRICKY = ["Dijkstra?", "Tag#1", "A B", "정렬?"]


def _record_requests():
    calls = []

    def fake_get(url, **kw):
        calls.append(("GET", url))
        resp = MagicMock()
        resp.status_code = 404
        return resp

    def fake_put(url, **kw):
        calls.append(("PUT", url))
        resp = MagicMock()
        resp.status_code = 201
        resp.raise_for_status.return_value = None
        return resp

    return calls, fake_get, fake_put


@pytest.mark.parametrize("title", _TRICKY)
def test_readme_and_code_reach_distinct_paths(title):
    calls, fake_get, fake_put = _record_requests()
    folder, _ = build_solution_target("codeforces", "20C", title)
    with patch.object(gh.requests, "get", fake_get), patch.object(gh.requests, "put", fake_put):
        gh.push_file_to_github("me/solutions", "t", f"{folder}/README.md", "x", "m")
        gh.push_file_to_github("me/solutions", "t", f"{folder}/main.cpp", "x", "m")

    puts = [url for method, url in calls if method == "PUT"]
    assert len(set(puts)) == 2, f"두 PUT 이 같은 경로로 갔다: {puts}"
    for url in puts:
        assert "?" not in url, f"경로가 쿼리스트링으로 잘렸다: {url}"
        assert "#" not in url, f"경로가 프래그먼트로 잘렸다: {url}"
    assert puts[0].endswith("/README.md")
    assert puts[1].endswith("/main.cpp")


@pytest.mark.parametrize("title", _TRICKY)
def test_sha_lookup_uses_the_same_encoded_path(title):
    """PUT 과 sha 조회가 다른 경로를 보면, 있는 파일을 새 파일로 오인해 422 가 된다."""
    calls, fake_get, fake_put = _record_requests()
    folder, _ = build_solution_target("boj", 1000, title, "Gold V")
    with patch.object(gh.requests, "get", fake_get), patch.object(gh.requests, "put", fake_put):
        gh.push_file_to_github("me/solutions", "t", f"{folder}/README.md", "x", "m")

    gets = [url for method, url in calls if method == "GET"]
    puts = [url for method, url in calls if method == "PUT"]
    assert gets == puts


@pytest.mark.parametrize("title", _TRICKY)
def test_raw_content_url_is_encoded_too(title):
    """가져오기가 읽는 raw 경로도 같은 규칙을 따른다 — 트리 API 가 준 경로에 그 문자가 있다."""
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.text = "content"
        return resp

    with patch.object(gh.requests, "get", fake_get):
        gh.get_raw_github_content("me/solutions", f"백준/Gold/1000번. {title}/README.md")

    assert "?" not in seen["url"] and "#" not in seen["url"], seen["url"]
    assert seen["url"].endswith("/README.md")
