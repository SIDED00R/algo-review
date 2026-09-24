"""/api/import-leetcode — 클라이언트 대역으로 저장 행·중복·세션 우선순위·push·오류 매핑을 본다."""
import db
from clients import UpstreamUnavailable
from routes import import_leetcode

_SUB = {
    "problem_ref": "two-sum", "problem_id": 1, "title": "Two Sum", "tier": 1, "tier_name": "LeetCode Easy",
    "tags": ["Array"], "language": "Python 3", "code": "print(1)",
    "problem_url": "https://leetcode.com/problems/two-sum/",
}
_SQL_SUB = dict(_SUB, problem_ref="second-highest-salary", problem_id=176, title="Second Highest Salary",
                tier=2, tier_name="LeetCode Medium", tags=["Database"], language="MySQL", code="")


def test_import_saves_new_rows_and_skips_existing(minimal_app, monkeypatch):
    seen = {}

    def _subs(username, count=20, session=None):
        seen.update(username=username, count=count, session=session)
        return [dict(_SUB), dict(_SQL_SUB)]

    monkeypatch.setattr(import_leetcode.api_client, "get_leetcode_user_submissions", _subs)
    monkeypatch.setattr(import_leetcode.settings, "leetcode_session", "from-env")
    client = minimal_app(import_leetcode.router)

    r = client.post("/api/import-leetcode", json={"username": "me", "count": 50})
    assert r.status_code == 200, r.text
    assert r.json() == {"username": "me", "total_found": 2, "imported": 2, "skipped": 0,
                        "has_source": True, "github_pushed": 0, "github_repo": ""}
    assert seen == {"username": "me", "count": 50, "session": "from-env"}

    rows = {p["problem_ref"]: p for p in db.get_solved_history(platform="leetcode", per_page=10)["problems"]}
    assert rows["two-sum"]["problem_id"] == 1
    assert rows["two-sum"]["tier_name"] == "LeetCode Easy"
    assert rows["two-sum"]["has_code"]
    assert rows["second-highest-salary"]["language"] == "MySQL"
    assert not rows["second-highest-salary"]["has_code"]

    again = client.post("/api/import-leetcode", json={"username": "me", "count": 50}).json()
    assert (again["imported"], again["skipped"]) == (0, 2)


def test_request_session_wins_and_solutions_push_to_the_leetcode_folder(minimal_app, monkeypatch):
    seen, pushed = {}, []
    monkeypatch.setattr(import_leetcode.settings, "leetcode_session", "from-env")
    monkeypatch.setattr(import_leetcode.api_client, "get_leetcode_user_submissions",
                        lambda username, count=20, session=None: seen.update(session=session) or [dict(_SUB)])
    monkeypatch.setattr(import_leetcode, "push_solution",
                        lambda repo, token, folder, stem, ext, code, readme, msg:
                        pushed.append((repo, folder, stem + ext, msg, "## 문제 설명" in readme)) or True)

    r = minimal_app(import_leetcode.router).post("/api/import-leetcode", json={
        "username": "me", "count": 5, "session": "from-request", "github_repo": "u/r", "github_token": "t"})
    assert r.json()["github_pushed"] == 1
    assert seen == {"session": "from-request"}
    assert pushed == [("u/r", "LeetCode/Easy/two-sum. Two Sum", "two-sum.py", "[LeetCode] two-sum. Two Sum", False)]


def test_upstream_and_input_errors_map_to_502_and_400(minimal_app, monkeypatch):
    client = minimal_app(import_leetcode.router)

    def _raise(exc):
        return lambda *a, **k: (_ for _ in ()).throw(exc)

    monkeypatch.setattr(import_leetcode.api_client, "get_leetcode_user_submissions",
                        _raise(UpstreamUnavailable("LeetCode API 오류 (HTTP 503)")))
    assert client.post("/api/import-leetcode", json={"username": "me"}).status_code == 502

    monkeypatch.setattr(import_leetcode.api_client, "get_leetcode_user_submissions",
                        _raise(ValueError("LEETCODE_SESSION 이 만료됐거나 잘못됐습니다.")))
    r = client.post("/api/import-leetcode", json={"username": "me"})
    assert r.status_code == 400 and "만료" in r.json()["detail"]

    assert client.post("/api/import-leetcode", json={"username": "   "}).status_code == 422


def test_demo_mode_blocks_import(minimal_app, monkeypatch):
    monkeypatch.setattr(import_leetcode, "IS_DEMO", True)
    assert minimal_app(import_leetcode.router).post("/api/import-leetcode", json={"username": "me"}).status_code == 403
