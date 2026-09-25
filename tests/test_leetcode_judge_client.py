"""clients/leetcode_judge — requests.Session 대역으로 자격증명 순서·쿠키 갱신 저장·결과 정규화·오류 매핑을 본다. 네트워크 없음."""
import json

import pytest
from requests.cookies import RequestsCookieJar

import db
from clients import leetcode_judge as judge
from clients.utils import UpstreamUnavailable


class _Resp:
    def __init__(self, payload, status=200, content_type="application/json", headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.cookies = RequestsCookieJar()

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _FakeSession:
    """post 는 스크립트(응답 목록)를 차례로, get(폴링)은 poll 목록을 차례로 돌려준다.

    쿠키 항아리는 진짜 RequestsCookieJar 다 — 서버가 `Domain=.leetcode.com` 으로 내려 주는 갱신 쿠키는
    우리가 `leetcode.com` 으로 넣은 것과 별개 항목으로 들어간다(실측). 그 차이를 흉내 내야 갱신 저장 결함이 보인다.
    """
    script = []
    polls = []
    calls = []
    refreshed_session = None   # 성공 응답에 실어 줄 새 LEETCODE_SESSION 값

    def __init__(self):
        self.cookies = RequestsCookieJar()
        self.headers = {}

    def post(self, url, data=None, timeout=None):
        payload = json.loads(data)
        self.calls.append({"url": url, "session": self.cookies.get("LEETCODE_SESSION", domain="leetcode.com"),
                           "csrf": self.headers.get("x-csrftoken"), "payload": payload})
        resp = self.script.pop(0)
        if resp.status_code == 200 and self.refreshed_session:
            for jar in (self.cookies, resp.cookies):
                jar.set("LEETCODE_SESSION", self.refreshed_session, domain=".leetcode.com", path="/")
        return resp

    def get(self, url, timeout=None):
        self.calls.append({"url": url})
        return self.polls.pop(0)


@pytest.fixture
def fake(monkeypatch):
    _FakeSession.script, _FakeSession.polls, _FakeSession.calls = [], [], []
    _FakeSession.refreshed_session = None
    monkeypatch.setattr(judge.requests, "Session", _FakeSession)
    monkeypatch.setattr(judge, "_POLL_INTERVAL_SEC", 0)
    monkeypatch.setattr(judge.settings, "leetcode_session", "env-session")
    monkeypatch.setattr(judge.settings, "leetcode_csrftoken", "env-csrf")
    return _FakeSession


def test_split_example_cases_uses_param_count_and_falls_back_to_one_case():
    meta = json.dumps({"params": [{"name": "nums"}, {"name": "target"}]})
    assert judge.split_example_cases("[2,7]\n9\n[3,3]\n6", meta) == ["[2,7]\n9", "[3,3]\n6"]
    # Database 문제는 한 줄이 한 케이스(예제마다 테이블 JSON 한 줄) — 176 은 2줄 = 2케이스
    assert judge.split_example_cases("{\"headers\":[]}\n{\"rows\":[]}", '{"database": true, "mysql": []}') == \
        ["{\"headers\":[]}", "{\"rows\":[]}"]
    # 인자 수를 모르거나 줄 수가 맞지 않으면 통째로 한 케이스
    assert judge.split_example_cases("[2,7]\n9\n[3,3]", meta) == ["[2,7]\n9\n[3,3]"]
    assert judge.split_example_cases("[2,7]\n9", "not json") == ["[2,7]\n9"]
    assert judge.split_example_cases("", meta) == []


def test_case_count_mismatch_with_the_judge_is_not_reported_as_pass(fake):
    # 채점기가 2케이스로 판정했는데 우리가 1케이스로 나눴다면(둘째 케이스가 틀려도) 통과로 보이면 안 된다.
    fake.script = [_Resp({"interpret_id": "run_3"})]
    fake.polls = [_Resp({"state": "SUCCESS", "run_success": True, "status_msg": "Accepted",
                         "code_answer": ["200", "{}"], "expected_code_answer": ["200", "null"],
                         "compare_result": "10"})]
    result = judge.run_examples("second-highest-salary", "176", "mysql", "select 1", ["a\nb"])
    assert not result["run_success"]
    assert "2개 케이스로 판정" in result["error"] and "1개로 나뉘었습니다" in result["error"]
    assert result["cases"][0]["passed"] is False


def test_db_outage_falls_back_to_env_credentials_and_store_failure_is_swallowed(fake, monkeypatch):
    from sqlalchemy.exc import OperationalError
    monkeypatch.setattr(db, "cache_get_stale",
                        lambda key: (_ for _ in ()).throw(OperationalError("SELECT", {}, Exception("db down"))))
    fake.script = [_Resp({"interpret_id": "run_4"})]
    fake.polls = [_Resp({"state": "SUCCESS", "run_success": True, "status_msg": "Accepted",
                         "code_answer": ["[0,1]"], "expected_code_answer": ["[0,1]"], "compare_result": "1"})]
    fake.refreshed_session = "fresh"
    monkeypatch.setattr(db, "cache_set",
                        lambda key, payload: (_ for _ in ()).throw(OperationalError("INSERT", {"session": "fresh"},
                                                                                     Exception("db down"))))
    result = judge.run_examples("two-sum", "1", "python3", "code", ["[2,7]\n9"])
    assert result["run_success"] and fake.calls[0]["session"] == "env-session", "DB 없이 설정값으로 호출한다"


def test_poll_failure_after_submission_is_accepted_points_to_the_record(fake, monkeypatch):
    monkeypatch.setattr(judge, "_POLL_TIMEOUT_SEC", 0)
    fake.script = [_Resp({"submission_id": 80})]
    with pytest.raises(UpstreamUnavailable, match="다시 제출하지 말고") as info:
        judge.submit_solution("two-sum", "1", "python3", "code")
    assert "https://leetcode.com/submissions/detail/80/" in str(info.value)
    assert "다시 시도" not in str(info.value)


def test_run_examples_normalizes_per_case_results_and_stores_refreshed_cookie(fake):
    fake.script = [_Resp({"interpret_id": "run_1"})]
    fake.polls = [_Resp({"state": "PENDING"}),
                  _Resp({"state": "SUCCESS", "run_success": True, "status_msg": "Accepted",
                         "code_answer": ["[0,1]", "[9]"], "expected_code_answer": ["[0,1]", "[1,2]"],
                         "compare_result": "10", "status_runtime": "0 ms"})]
    fake.refreshed_session = "refreshed-session"

    result = judge.run_examples("two-sum", "1", "python3", "print(1)", ["[2,7]\n9", "[3,2,4]\n6"])

    assert result["status_msg"] == "Accepted" and result["run_success"] and result["runtime"] == "0 ms"
    assert result["cases"] == [
        {"input": "[2,7]\n9", "expected": "[0,1]", "actual": "[0,1]", "passed": True},
        {"input": "[3,2,4]\n6", "expected": "[1,2]", "actual": "[9]", "passed": False},
    ]
    post = fake.calls[0]
    assert post["url"].endswith("/problems/two-sum/interpret_solution/")
    assert post["payload"] == {"lang": "python3", "question_id": "1", "typed_code": "print(1)",
                               "data_input": "[2,7]\n9\n[3,2,4]\n6"}
    assert (post["session"], post["csrf"]) == ("env-session", "env-csrf")
    assert fake.calls[1]["url"].endswith("/submissions/detail/run_1/check/")
    # 갱신된 세션은 저장돼 다음 호출의 첫 후보가 된다.
    assert db.cache_get_stale(judge.SESSION_CACHE_KEY) == {"session": "refreshed-session", "csrf": "env-csrf"}
    fake.script = [_Resp({"interpret_id": "run_2"})]
    fake.polls = [_Resp({"state": "SUCCESS", "run_success": False, "status_msg": "Compile Error",
                         "full_compile_error": "SyntaxError"})]
    fake.refreshed_session = None
    result = judge.run_examples("two-sum", "1", "python3", "bad", ["[2,7]\n9"])
    assert fake.calls[-2]["session"] == "refreshed-session"
    assert not result["run_success"] and result["error"] == "SyntaxError"
    assert result["cases"] == [{"input": "[2,7]\n9", "expected": "", "actual": "", "passed": False}]


def test_stored_session_that_fails_falls_back_to_env_once(fake):
    db.cache_set(judge.SESSION_CACHE_KEY, {"session": "stale", "csrf": "stale-csrf"})
    fake.script = [_Resp({}, status=403), _Resp({"submission_id": 77})]
    fake.polls = [_Resp({"state": "SUCCESS", "status_msg": "Accepted", "total_correct": 65, "total_testcases": 65,
                         "status_runtime": "0 ms", "status_memory": "20 MB"})]

    result = judge.submit_solution("two-sum", "1", "python3", "code")

    assert [c["session"] for c in fake.calls[:2]] == ["stale", "env-session"]
    assert result == {"submission_id": "77", "url": "https://leetcode.com/submissions/detail/77/",
                      "status_msg": "Accepted", "accepted": True, "total_correct": 65, "total_testcases": 65,
                      "runtime": "0 ms", "memory": "20 MB", "error": "", "last_testcase": "",
                      "expected_output": "", "code_output": ""}


def test_wrong_answer_submission_carries_the_failing_case(fake):
    fake.script = [_Resp({"submission_id": 78})]
    fake.polls = [_Resp({"state": "SUCCESS", "status_msg": "Wrong Answer", "total_correct": 3, "total_testcases": 65,
                         "last_testcase": "[3,3]\n6", "expected_output": "[0,1]", "code_output": "[1,1]"})]
    result = judge.submit_solution("two-sum", "1", "cpp", "code")
    assert not result["accepted"]
    assert (result["last_testcase"], result["expected_output"], result["code_output"]) == ("[3,3]\n6", "[0,1]", "[1,1]")


@pytest.mark.parametrize("resp, exc, fragment", [
    (_Resp({}, status=401), judge.LeetCodeSessionError, "만료"),
    # Cloudflare 봇 확인 — 세션 문제가 아니다(실측: 연속 호출 뒤 인증된 요청도 받는다)
    (_Resp("<html>Just a moment...</html>", status=403, content_type="text/html; charset=UTF-8",
           headers={"cf-mitigated": "challenge"}), judge.LeetCodeChallenged, "Cloudflare"),
    (_Resp("<html>login</html>", content_type="text/html; charset=utf-8"), judge.LeetCodeSessionError, "만료"),
    (_Resp({}, status=429), judge.LeetCodeRateLimited, "제한"),
    (_Resp({}, status=502), UpstreamUnavailable, "HTTP 502"),
    (_Resp("garbage", content_type="text/plain"), UpstreamUnavailable, "해석"),
])
def test_http_failures_map_to_session_or_upstream_errors(fake, resp, exc, fragment):
    fake.script = [resp]
    with pytest.raises(exc, match=fragment):
        judge.submit_solution("two-sum", "1", "python3", "code")


def test_cloudflare_challenge_does_not_fall_back_to_the_next_credential(fake):
    db.cache_set(judge.SESSION_CACHE_KEY, {"session": "stored", "csrf": "stored-csrf"})
    fake.script = [_Resp("<html>Just a moment...</html>", status=403, content_type="text/html",
                         headers={"cf-mitigated": "challenge"}), _Resp({"submission_id": 1})]
    with pytest.raises(judge.LeetCodeChallenged):
        judge.submit_solution("two-sum", "1", "python3", "code")
    assert len(fake.calls) == 1, "챌린지는 자격증명 문제가 아니라 설정값으로 재시도하지 않는다"


def test_missing_credentials_and_poll_timeout(fake, monkeypatch):
    monkeypatch.setattr(judge.settings, "leetcode_session", None)
    with pytest.raises(judge.LeetCodeSessionError, match="설정되지 않았습니다"):
        judge.submit_solution("two-sum", "1", "python3", "code")
    assert fake.calls == [], "자격증명이 없으면 LeetCode 를 부르지 않는다"

    monkeypatch.setattr(judge.settings, "leetcode_session", "env-session")
    monkeypatch.setattr(judge, "_POLL_TIMEOUT_SEC", 0)
    # 예제 실행은 기록이 남지 않으니 폴링 시간 초과를 그대로 알린다(제출은 위 테스트처럼 접수 안내로 바뀐다).
    fake.script = [_Resp({"interpret_id": "run_79"})]
    with pytest.raises(UpstreamUnavailable, match="시간이 초과"):
        judge.run_examples("two-sum", "1", "python3", "code", ["[2,7]\n9"])
