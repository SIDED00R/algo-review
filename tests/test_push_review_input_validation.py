"""`/api/push-review` 의 문제 번호·제목 검증.

인증 없는 공개 엔드포인트이고, 받은 값이 그대로 저장소 폴더 경로가 되며 사용자의 GitHub
토큰으로 커밋된다. 검증이 스크래핑 분기 안에만 있으면 본문을 함께 보낸 요청이 통째로
건너뛴다.
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routes.helpers as helpers
from routes import github_push
from routes.helpers import build_solution_target, require_problem_ref, safe_path_segment


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(github_push.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def captured():
    seen = {}

    def _push(repo, token, files, message):
        seen["paths"] = [f["path"] for f in files]
        return True

    with patch.object(helpers.db, "get_github_settings",
                      return_value={"target_repo": "me/x", "access_token": "t"}), \
         patch.object(helpers.api_client, "push_files_to_github", _push), \
         patch.object(github_push, "IS_DEMO", False):
        yield seen


def _body(**kw):
    base = {"platform": "boj", "problem_ref": "1000", "title": "A+B", "tier_name": "Bronze V",
            "code": "print(1)", "language": "Python 3", "description": "본문"}
    base.update(kw)
    return base


@pytest.mark.parametrize("platform,ref", [
    ("codeforces", "zzz"), ("codeforces", "-"), ("boj", "abc"), ("boj", "1a"),
])
def test_a_malformed_problem_ref_is_a_400(client, captured, platform, ref):
    """형식 오류가 500 "서버 내부 오류" 로 새면 사용자는 무엇을 고칠지 알 수 없다.

    본문을 함께 보내 스크래핑 분기를 건너뛰게 해도 걸러져야 한다.
    (빈 문자열은 pydantic 이 422 로 먼저 막으므로 여기 목록에 없다.)
    """
    r = client.post("/api/push-review", json=_body(platform=platform, problem_ref=ref))
    assert r.status_code == 400, r.text
    assert "paths" not in captured, f"검증에 걸렸는데 커밋이 나갔다: {captured}"


def test_a_valid_request_still_pushes(client, captured):
    r = client.post("/api/push-review", json=_body())
    assert r.status_code == 200, r.text
    assert captured["paths"] == ["백준/Bronze/1000번. A+B/README.md",
                                 "백준/Bronze/1000번. A+B/print(1)" .replace("print(1)", "1000.py")]


def test_a_slash_in_the_title_stays_inside_one_folder(client, captured):
    """제목의 `/` 가 폴더 깊이를 늘리면 재가져오기 파서(4세그먼트 규약)가 그 문제를
    조용히 빠뜨린다 — `/api/import-github` 목록에서 사라진다."""
    r = client.post("/api/push-review", json=_body(problem_ref="1806", title="부분합/합계",
                                                   tier_name="Gold IV"))
    assert r.status_code == 200, r.text
    for path in captured["paths"]:
        assert len(path.split("/")) == 4, f"세그먼트가 {len(path.split('/'))}개다: {path}"


@pytest.mark.parametrize("title,expected", [
    ("부분합/합계", "부분합-합계"),
    (r"A\B", "A-B"),
    ("  ...  ", "제목 없음"),
    ("Normal Title", "Normal Title"),
    ("Dijkstra?", "Dijkstra?"),        # 인코딩이 처리한다 — 폴더명을 바꾸지 않는다
])
def test_path_segment_sanitisation(title, expected):
    assert safe_path_segment(title) == expected


def test_codeforces_ref_is_normalised_before_it_becomes_a_path():
    """`4/A` 와 `4a` 가 서로 다른 폴더를 만들면 같은 문제가 저장소에 둘로 남는다."""
    assert require_problem_ref("codeforces", "4/A") == "4A"
    assert require_problem_ref("codeforces", "4a") == "4A"
    assert build_solution_target("codeforces", "4A", "Watermelon")[0] == "Codeforces/4A. Watermelon"


def test_require_problem_ref_raises_http_400():
    for platform, ref in (("boj", "abc"), ("codeforces", "zzz")):
        with pytest.raises(HTTPException) as caught:
            require_problem_ref(platform, ref)
        assert caught.value.status_code == 400
