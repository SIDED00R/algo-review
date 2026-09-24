"""LeetCode 클라이언트 — GraphQL·REST 응답을 대역으로 두고 스냅샷·조회·검색·제출 파싱을 본다. 네트워크 없음."""
import pytest
import requests

import db
from clients import leetcode as lc
from clients.utils import ProblemNotFound, ProblemSearchError, UpstreamUnavailable


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _q(slug, fid, difficulty, tags, paid=False, category="Algorithms"):
    return {
        "titleSlug": slug, "title": slug.replace("-", " ").title(), "questionFrontendId": str(fid),
        "difficulty": difficulty, "isPaidOnly": paid, "categoryTitle": category,
        "topicTags": [{"name": t, "slug": t.lower().replace(" ", "-")} for t in tags],
    }


_QUESTIONS = [
    _q("two-sum", 1, "Easy", ["Array", "Hash Table"]),
    _q("add-two-numbers", 2, "Medium", ["Linked List", "Math"]),
    _q("climbing-stairs", 70, "Easy", ["Dynamic Programming", "Math"]),
    _q("edit-distance", 72, "Hard", ["Dynamic Programming", "String"]),
    _q("combine-two-tables", 175, "Easy", ["Database"], category="Database"),
    _q("consecutive-available-seats", 603, "Easy", ["Database"], paid=True, category="Database"),
]
_ACS = {"two-sum": 100, "add-two-numbers": 50, "climbing-stairs": 80, "edit-distance": 10,
        "combine-two-tables": 60, "consecutive-available-seats": 5}
_CONTENT = "<p>Given <code>nums</code>, 10<sup>9</sup></p><pre>Input: a\nOutput: b</pre>"


@pytest.fixture
def fake_api(monkeypatch):
    """requests.post/get 대역. 호출을 기록하고 페이지 크기를 시험용으로 줄인다."""
    calls = {"post": [], "get": []}
    monkeypatch.setattr(lc, "_PAGE_SIZE", 4)
    monkeypatch.setattr(lc, "_REQUEST_DELAY_SEC", 0)

    def _post(url, json=None, headers=None, cookies=None, timeout=None):
        query, variables = json["query"], json["variables"]
        calls["post"].append({"query": query, "variables": variables, "cookies": cookies})
        if "questionList(" in query:
            skip, limit = variables["skip"], variables["limit"]
            return _Resp({"data": {"questionList": {"totalNum": len(_QUESTIONS),
                                                    "data": _QUESTIONS[skip:skip + limit]}}})
        if "question(titleSlug" in query:
            found = next((q for q in _QUESTIONS if q["titleSlug"] == variables["slug"]), None)
            if found is None:
                return _Resp({"data": {"question": None}})
            return _Resp({"data": {"question": {**found, "content": None if found["isPaidOnly"] else _CONTENT}}})
        if "recentAcSubmissionList" in query:
            return _Resp({"data": {"recentAcSubmissionList": [
                {"id": "1", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "2", "lang": "python3"},
                {"id": "2", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1", "lang": "python3"},
                {"id": "3", "title": "Add Two Numbers", "titleSlug": "add-two-numbers", "timestamp": "0",
                 "lang": "mysql"},
            ]}})
        if "userStatus" in query:
            signed = bool(cookies) and cookies.get("LEETCODE_SESSION") == "good"
            return _Resp({"data": {"userStatus": {"isSignedIn": signed, "username": "me" if signed else ""}}})
        if "submissionList(" in query:
            page = variables["offset"] // 20
            rows = [
                [{"id": "11", "statusDisplay": "Wrong Answer", "lang": "python3", "timestamp": "3",
                  "title": "Two Sum", "titleSlug": "two-sum"},
                 {"id": "12", "statusDisplay": "Accepted", "lang": "python3", "timestamp": "2",
                  "title": "Two Sum", "titleSlug": "two-sum"}],
                [{"id": "13", "statusDisplay": "Accepted", "lang": "mysql", "timestamp": "1",
                  "title": "Combine Two Tables", "titleSlug": "combine-two-tables"}],
            ]
            return _Resp({"data": {"submissionList": {"lastKey": "k", "hasNext": page == 0,
                                                      "submissions": rows[page] if page < 2 else []}}})
        if "submissionDetails" in query:
            return _Resp({"data": {"submissionDetails": {"code": f"code-{variables['id']}", "lang": {"name": "x"}}}})
        raise AssertionError(f"대역이 모르는 쿼리: {query[:60]}")

    def _get(url, headers=None, timeout=None):
        calls["get"].append(url)
        return _Resp({"stat_status_pairs": [
            {"stat": {"question__title_slug": slug, "total_acs": n}} for slug, n in _ACS.items()]})

    monkeypatch.setattr(lc.requests, "post", _post)
    monkeypatch.setattr(lc.requests, "get", _get)
    return calls


def _down(*args, **kwargs):
    raise requests.ConnectionError("down")


def test_snapshot_pages_through_the_list_and_merges_popularity(fake_api):
    items = lc._get_lc_snapshot()
    assert [i["slug"] for i in items] == [q["titleSlug"] for q in _QUESTIONS]
    list_calls = [c for c in fake_api["post"] if "questionList(" in c["query"]]
    assert [c["variables"]["skip"] for c in list_calls] == [0, 4], "6개를 4개씩 두 페이지로 받아야 한다"
    assert lc._by_slug["two-sum"]["total_acs"] == 100
    assert lc._by_id[175]["slug"] == "combine-two-tables"
    # 두 번째 조회는 프로세스 캐시 — 네트워크 호출이 없다.
    before = len(fake_api["post"])
    lc._get_lc_snapshot()
    assert len(fake_api["post"]) == before


def test_snapshot_is_persisted_in_api_cache_for_a_day(fake_api):
    lc._get_lc_snapshot()
    assert db.cache_get(lc.SNAPSHOT_CACHE_KEY, lc.SNAPSHOT_TTL_SEC)
    # 프로세스 캐시를 비워도(재기동) DB 캐시가 있으면 원격을 부르지 않는다.
    lc._snapshot = lc._by_slug = lc._by_id = None
    before = len(fake_api["post"])
    assert [i["slug"] for i in lc._get_lc_snapshot()][:1] == ["two-sum"]
    assert len(fake_api["post"]) == before


def test_a_failed_page_installs_nothing(fake_api, monkeypatch):
    real_post = lc.requests.post

    def _flaky(url, json=None, **kwargs):
        if "questionList(" in json["query"] and json["variables"]["skip"] > 0:
            raise requests.ConnectionError("boom")
        return real_post(url, json=json, **kwargs)

    monkeypatch.setattr(lc.requests, "post", _flaky)
    with pytest.raises(UpstreamUnavailable):
        lc._get_lc_snapshot()
    assert lc._snapshot is None, "부분 스냅샷이 설치됐다"
    assert db.cache_get_stale(lc.SNAPSHOT_CACHE_KEY) is None


def test_stale_cache_is_used_when_the_remote_fails(fake_api, monkeypatch):
    lc._get_lc_snapshot()
    lc._snapshot = lc._by_slug = lc._by_id = None
    monkeypatch.setattr(db, "cache_get", lambda key, max_age_sec: None)   # 하루가 지났다
    monkeypatch.setattr(lc.requests, "post", _down)
    assert lc._by_id is None
    assert [i["slug"] for i in lc._get_lc_snapshot()][:1] == ["two-sum"]


def test_problem_info_accepts_number_slug_and_url(fake_api):
    by_number = lc.get_leetcode_problem_info("175")
    assert by_number == lc.get_leetcode_problem_info("combine-two-tables")
    assert by_number == lc.get_leetcode_problem_info("https://leetcode.com/problems/Combine-Two-Tables/description/")
    assert by_number == {
        "id": 175, "platform": "leetcode", "problem_ref": "combine-two-tables", "title": "Combine Two Tables",
        "tier": 1, "tier_name": "LeetCode Easy", "tags": ["Database"],
        "url": "https://leetcode.com/problems/combine-two-tables/",
    }


def test_unknown_problem_and_bad_format_are_value_errors(fake_api):
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        lc.get_leetcode_problem_info("no-such-slug")
    with pytest.raises(ValueError, match="slug"):
        lc.normalize_leetcode_problem_ref("Bad Slug!")
    with pytest.raises(ValueError):
        lc.normalize_leetcode_problem_ref("175")   # 번호는 스냅샷이 필요해 정규화 함수가 받지 않는다


def test_statement_text_keeps_pre_lines_and_marks_superscripts(fake_api):
    text = lc.get_leetcode_problem_statement("two-sum")
    assert "10^9" in text
    assert "Input: a\nOutput: b" in text
    assert "<" not in text


def test_paid_problem_statement_is_a_failure_string(fake_api):
    from routes.problem_resolve import is_scrape_failure
    assert is_scrape_failure(lc.get_leetcode_problem_statement("consecutive-available-seats"))
    assert lc.get_lc_problem_sections("consecutive-available-seats") is None
    assert lc.get_lc_problem_sections("two-sum") == {"description": lc.get_leetcode_problem_statement("two-sum"),
                                                    "input": "", "output": ""}


def test_scrape_returns_viewer_fields_and_not_found(fake_api):
    raw = lc.scrape_lc_problem("two-sum")
    assert (raw["problem_id"], raw["tier"], raw["category"], raw["is_paid_only"]) == (1, 1, "Algorithms", False)
    assert "<sup>" in raw["content_html"]
    with pytest.raises(ProblemNotFound):
        lc.scrape_lc_problem("no-such-slug")


def test_search_by_tag_excludes_paid_and_sorts_by_popularity(fake_api):
    found = lc.search_lc_problems_by_tag("Dynamic Programming", 1, 3, set())
    assert [p["id"] for p in found] == ["climbing-stairs", "edit-distance"]
    assert found[0] == {"id": "climbing-stairs", "problem_id": 70, "title": "Climbing Stairs", "tier": 1,
                        "tier_name": "Easy", "url": "https://leetcode.com/problems/climbing-stairs/"}
    # slug 로도 찾고, 유료 문제는 빠진다.
    assert [p["id"] for p in lc.search_lc_problems_by_tag("database", 1, 3, set())] == ["combine-two-tables"]
    assert lc.search_lc_problems_by_tag("dynamic-programming", 3, 3, {"edit-distance"}) == []


def test_search_failure_is_a_problem_search_error(monkeypatch):
    monkeypatch.setattr(lc.requests, "post", _down)
    with pytest.raises(ProblemSearchError):
        lc.search_lc_problems_by_tag("math", 1, 3, set())


def test_public_submissions_dedupe_per_problem_and_carry_no_code(fake_api):
    subs = lc.get_leetcode_user_submissions("someone", 20)
    assert [(s["problem_ref"], s["language"], s["code"]) for s in subs] == [
        ("two-sum", "Python 3", ""), ("add-two-numbers", "MySQL", "")]
    assert subs[0]["tier_name"] == "LeetCode Easy"
    assert subs[0]["tags"] == ["Array", "Hash Table"]
    assert subs[0]["problem_id"] == 1


def test_session_submissions_page_and_fetch_code(fake_api):
    subs = lc.get_leetcode_user_submissions("me", 20, session="good")
    assert [(s["problem_ref"], s["code"]) for s in subs] == [("two-sum", "code-12"), ("combine-two-tables", "code-13")]
    detail_calls = [c for c in fake_api["post"] if "submissionDetails" in c["query"]]
    assert len(detail_calls) == 2
    assert all(c["cookies"] == {"LEETCODE_SESSION": "good"} for c in detail_calls)


def test_expired_session_and_wrong_account_are_rejected(fake_api):
    with pytest.raises(ValueError, match="만료"):
        lc.get_leetcode_user_submissions("me", 5, session="bad")
    with pytest.raises(ValueError, match="다릅니다"):
        lc.get_leetcode_user_submissions("other", 5, session="good")


def test_graphql_errors_and_http_failures_map_to_the_right_exceptions(monkeypatch):
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: _Resp({"errors": [{"message": "nope"}]}))
    with pytest.raises(ValueError, match="nope"):
        lc._lc_graphql("query{x}")
    monkeypatch.setattr(lc.requests, "post", lambda *a, **k: _Resp({}, status=503))
    with pytest.raises(UpstreamUnavailable):
        lc._lc_graphql("query{x}")
    monkeypatch.setattr(lc.requests, "post", _down)
    with pytest.raises(UpstreamUnavailable):
        lc._lc_graphql("query{x}")
