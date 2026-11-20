"""/api/problem/lookup — 번호·slug·URL → 뷰어용 정규 ref + 메타. 외부 조회는 clients 대역으로 끊는다."""
import pytest

import clients as api_client
from clients import UpstreamUnavailable
from routes import problem_lookup as lookup_route

_CF = {"id": 0, "platform": "codeforces", "problem_ref": "4A", "title": "Watermelon", "tier": 0,
       "tier_name": "Codeforces 800", "tags": ["math"],
       "url": "https://codeforces.com/problemset/problem/4/A"}
_LC = {"id": 1, "platform": "leetcode", "problem_ref": "two-sum", "title": "Two Sum", "tier": 1,
       "tier_name": "Easy", "tags": ["Array"], "url": "https://leetcode.com/problems/two-sum/"}


@pytest.fixture
def client(minimal_app):
    return minimal_app(lookup_route.router)


def _lookup(client, **params):
    return client.get("/api/problem/lookup", params=params)


def test_codeforces_input_is_passed_to_the_client_and_the_normalized_ref_comes_back(client, monkeypatch):
    calls = []
    monkeypatch.setattr(api_client, "get_codeforces_problem_info", lambda ref: calls.append(ref) or dict(_CF))

    resp = _lookup(client, platform="codeforces", ref="4/a")

    assert resp.status_code == 200
    assert resp.json() == {"platform": "codeforces", "problem_ref": "4A", "problem_id": None,
                           "title": "Watermelon", "tier_name": "Codeforces 800", "url": _CF["url"]}
    # 정규화는 클라이언트 조회가 한다 — 라우트는 입력을 손대지 않고 넘긴다.
    assert calls == ["4/a"]


def test_leetcode_number_resolves_to_the_slug_the_viewer_needs(client, monkeypatch):
    monkeypatch.setattr(api_client, "get_leetcode_problem_info", lambda ref: dict(_LC))

    body = _lookup(client, platform="leetcode", ref="1").json()

    assert (body["problem_ref"], body["problem_id"], body["title"], body["tier_name"]) == \
        ("two-sum", 1, "Two Sum", "Easy")


def test_unsupported_platform_is_rejected_before_any_lookup(client, monkeypatch):
    monkeypatch.setattr(api_client, "get_problem_info", lambda pid: pytest.fail("미지원 플랫폼을 조회했다"))

    resp = _lookup(client, platform="atcoder", ref="1000")

    assert resp.status_code == 400
    assert "지원하지 않는 플랫폼" in resp.json()["detail"]


def test_boj_number_resolves_through_solved_ac_without_the_db(client, monkeypatch):
    """백준은 DB 캐시(리뷰 기록)를 읽지 않는다 — DB 가 꺼져 있어도 뷰어를 열 수 있어야 한다."""
    import db
    monkeypatch.setattr(db, "get_cached_problem_info", lambda pid: pytest.fail("직접 열기가 DB 를 읽었다"))
    calls = []
    monkeypatch.setattr(api_client, "get_problem_info", lambda pid: calls.append(pid) or {
        "id": pid, "title": "RGB거리", "tier": 10, "tier_name": "Silver I", "tags": ["다이나믹 프로그래밍"]})

    resp = _lookup(client, platform="boj", ref=" 1149 ")

    assert resp.status_code == 200
    assert resp.json() == {"platform": "boj", "problem_ref": "1149", "problem_id": 1149, "title": "RGB거리",
                           "tier_name": "Silver I", "url": "https://boj.kr/1149"}
    assert calls == [1149]


@pytest.mark.parametrize("ref", ["", "abc", "12a", "-5"])
def test_boj_non_numeric_ref_is_a_400_without_any_lookup(client, monkeypatch, ref):
    monkeypatch.setattr(api_client, "get_problem_info", lambda pid: pytest.fail("형식 오류를 조회했다"))

    resp = _lookup(client, platform="boj", ref=ref)

    assert resp.status_code == 400
    assert "숫자" in resp.json()["detail"]


def test_boj_unknown_problem_is_400_and_solved_ac_outage_is_502(client, monkeypatch):
    import requests

    def missing(pid):
        resp = requests.Response()
        resp.status_code = 404
        raise requests.HTTPError("404 Client Error", response=resp)

    monkeypatch.setattr(api_client, "get_problem_info", missing)
    resp = _lookup(client, platform="boj", ref="999999")
    assert resp.status_code == 400
    assert "없는 문제" in resp.json()["detail"]

    def down(pid):
        raise requests.ConnectionError("solved.ac unreachable")

    monkeypatch.setattr(api_client, "get_problem_info", down)
    resp = _lookup(client, platform="boj", ref="1000")
    assert resp.status_code == 502
    assert "ConnectionError" in resp.json()["detail"]


def test_blank_ref_is_a_400_with_the_platform_hint(client, monkeypatch):
    monkeypatch.setattr(api_client, "get_codeforces_problem_info", lambda ref: pytest.fail("빈 입력을 조회했다"))

    resp = _lookup(client, platform="codeforces", ref="   ")

    assert resp.status_code == 400
    assert "4A" in resp.json()["detail"]


def test_unknown_problem_is_400_and_upstream_outage_is_502(client, monkeypatch):
    def not_found(ref):
        raise ValueError(f"Codeforces 문제를 찾을 수 없습니다: {ref}")

    monkeypatch.setattr(api_client, "get_codeforces_problem_info", not_found)
    resp = _lookup(client, platform="codeforces", ref="9999Z")
    assert resp.status_code == 400
    assert "찾을 수 없습니다" in resp.json()["detail"]

    def down(ref):
        raise UpstreamUnavailable("codeforces.com 연결 실패")

    monkeypatch.setattr(api_client, "get_codeforces_problem_info", down)
    assert _lookup(client, platform="codeforces", ref="4A").status_code == 502


def test_demo_answers_without_calling_any_client(client, monkeypatch):
    monkeypatch.setattr(lookup_route, "IS_DEMO", True)
    monkeypatch.setattr(api_client, "get_codeforces_problem_info", lambda ref: pytest.fail("데모가 외부 조회를 했다"))

    body = _lookup(client, platform="codeforces", ref="1530D").json()

    assert body["problem_ref"] == "1530D"
    assert body["platform"] == "codeforces"
