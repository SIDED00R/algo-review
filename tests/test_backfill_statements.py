"""백필 스크립트 검증.

README 파서는 `build_readme` 가 쓴 문서를 되읽는 것이므로, build_readme 로 만든 README 를
그대로 통과시켜 왕복을 고정한다 — 형식이 바뀌면 여기서 깨진다.
"""
import pytest

import backfill_statements as backfill
import db
from routes.helpers import build_readme
from routes.problem_resolve import is_scrape_failure


def test_parse_readme_roundtrips_build_readme_output():
    readme = build_readme(
        problem_ref="1000", title="A+B", tier_name="Bronze V", tags=["수학", "구현"],
        language="Python 3", url="https://boj.kr/1000",
        description="두 정수 A와 B를 입력받은 다음, A+B를 출력하는 프로그램을 작성하시오.",
        input_desc="첫째 줄에 A와 B가 주어진다. (0 < A, B < 10)",
        output_desc="첫째 줄에 A+B를 출력한다.",
        review={"efficiency": "good", "complexity": "O(1)", "feedback": "좋다",
                "strengths": ["간결"], "weaknesses": []},
    )
    statement = backfill.parse_readme_sections(readme)

    assert statement.startswith("【문제】")
    assert "【입력】" in statement and "【출력】" in statement
    assert "A+B를 출력하는 프로그램" in statement
    assert "0 < A, B < 10" in statement
    # 리뷰 섹션은 문제 본문이 아니다 — 섞여 들어오면 LLM 프롬프트가 오염된다.
    assert "좋다" not in statement
    assert "O(1)" not in statement
    assert "간결" not in statement
    # 머리말(제목·성능 요약·분류·제출 일자)도 본문이 아니다.
    assert "Bronze V" not in statement
    assert "성능 요약" not in statement


def test_parse_readme_without_statement_sections_returns_empty():
    """본문 없이 올라간 README — 여기서 빈 문자열이 나와야 백필이 SKIP 으로 처리한다."""
    readme = build_readme(problem_ref="1000", title="A+B", tier_name="Bronze V",
                          tags=[], language="Python 3", url="https://boj.kr/1000")
    assert backfill.parse_readme_sections(readme) == ""


def test_parse_readme_takes_only_present_sections():
    readme = build_readme(problem_ref="4A", title="Watermelon", tier_name="Codeforces 800",
                          tags=["math"], language="Python 3", url="https://codeforces.com/",
                          description="본문만 있고 입력·출력 섹션은 없다.")
    statement = backfill.parse_readme_sections(readme)
    assert statement == "【문제】\n본문만 있고 입력·출력 섹션은 없다."


def test_fetch_boj_statement_uses_solution_folder_path(monkeypatch):
    """폴더 경로는 build_solution_target 이 만든다 — 규칙을 복제하면 저장소와 어긋난다."""
    asked = []

    def fake_get(repo, path, token=None):
        asked.append((repo, path, token))
        return build_readme(problem_ref="1000", title="A+B", tier_name="Bronze V", tags=[],
                            language="Python 3", url="https://boj.kr/1000",
                            description="두 정수 A와 B를 입력받아 A+B를 출력하는 프로그램을 작성하시오.")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    problem = {"problem_ref": "1000", "name_candidates": [("A+B", "Bronze V")]}
    statement, source = backfill.fetch_boj_statement(problem, "me/solutions", "tok")

    assert asked == [("me/solutions", "백준/Bronze/1000번. A+B/README.md", "tok")]
    assert statement.startswith("【문제】")
    assert source == "백준/Bronze/1000번. A+B/README.md"


def test_fetch_boj_statement_falls_back_to_other_title(monkeypatch):
    """회차 사이에 제목이 바뀌면 폴더명이 달라진다 — 다른 회차 제목으로 재시도해야 한다."""
    def fake_get(repo, path, token=None):
        if "고친 제목" not in path:
            raise RuntimeError("404")
        return build_readme(problem_ref="1000", title="A+B 고친 제목", tier_name="Bronze V",
                            tags=[], language="Python 3", url="https://boj.kr/1000",
                            description="두 정수 A와 B를 입력받아 A+B를 출력하는 프로그램을 작성하시오.")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    problem = {"problem_ref": "1000",
               "name_candidates": [("A+B", "Bronze V"), ("A+B 고친 제목", "Bronze V")]}
    statement, source = backfill.fetch_boj_statement(problem, "me/solutions", "tok")
    assert statement.startswith("【문제】")
    assert "고친 제목" in source


def test_fetch_boj_statement_reports_when_no_readme(monkeypatch):
    def fake_get(repo, path, token=None):
        raise RuntimeError("404")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    problem = {"problem_ref": "1000", "name_candidates": [("A+B", "Bronze V")]}
    statement, source = backfill.fetch_boj_statement(problem, "me/solutions", "tok")
    assert statement == ""
    assert "README 를 찾지 못했다" in source


def test_fetch_boj_statement_reports_when_readme_lacks_sections(monkeypatch):
    """본문 없이 올라간 README — 조용히 빈 값을 저장하지 않고 이유를 보고해야 한다."""
    def fake_get(repo, path, token=None):
        return build_readme(problem_ref="1000", title="A+B", tier_name="Bronze V", tags=[],
                            language="Python 3", url="https://boj.kr/1000")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    problem = {"problem_ref": "1000", "name_candidates": [("A+B", "Bronze V")]}
    statement, source = backfill.fetch_boj_statement(problem, "me/solutions", "tok")
    assert statement == ""
    assert "문제 설명 섹션이 비었다" in source


def test_reason_bucket_collapses_paths_for_the_summary():
    """이유마다 경로가 붙으면 요약이 전부 다른 항목이 되어 의미를 잃는다."""
    a = "README 를 찾지 못했다 (시도: 백준/Gold/1654번. 랜선 자르기/README.md)"
    b = "README 를 찾지 못했다 (시도: 백준/Silver/1003번. 피보나치 함수/README.md)"
    assert backfill.reason_bucket(a) == backfill.reason_bucket(b) == "README 를 찾지 못했다"
    c = "README 는 있으나 문제 설명 섹션이 비었다: 백준/Gold/1654번. 랜선 자르기/README.md"
    assert backfill.reason_bucket(c) == "README 는 있으나 문제 설명 섹션이 비었다"
    assert backfill.reason_bucket("GitHub 미연결") == "GitHub 미연결"


def test_scrape_failure_strings_are_rejected():
    """수집 함수는 예외 대신 실패 문자열을 반환한다 — 저장하면 리뷰가 영구히 오염된다."""
    assert is_scrape_failure("크롤링 실패: 404 Client Error: Not Found for url: ...")
    assert is_scrape_failure("문제 설명을 가져올 수 없습니다.")
    assert is_scrape_failure("문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 "
                             "제한적으로 분석합니다.")
    assert is_scrape_failure("")
    assert is_scrape_failure("   ")
    assert not is_scrape_failure("【문제】\n두 정수 A와 B를 입력받아 A+B를 출력한다.")


def _seed(problem_ref: str, platform: str = "boj", title: str = "A+B",
          tier_name: str = "Bronze V", statement: str = ""):
    db.save_review(problem_id=int(problem_ref) if problem_ref.isdigit() else 0,
                   title=title, tier=1, tags=["수학"], code="print(1)", feedback="f",
                   efficiency="good", platform=platform, problem_ref=problem_ref,
                   tier_name=tier_name, language="Python 3", problem_statement=statement)


def test_missing_statement_groups_by_problem_and_collects_name_candidates(at_time):
    at_time("2024-01-01T00:00:00")
    _seed("1000", title="A+B")
    at_time("2024-01-02T00:00:00")
    _seed("1000", title="A+B 고친 제목")      # 제목이 바뀐 회차 — 폴더명 후보가 둘이 된다
    _seed("4A", platform="codeforces", title="Watermelon", tier_name="Codeforces 800")

    problems = db.get_problems_missing_statement()
    by_ref = {p["problem_ref"]: p for p in problems}
    assert by_ref["1000"]["empty_rows"] == 2
    assert set(by_ref["1000"]["name_candidates"]) == {("A+B", "Bronze V"),
                                                      ("A+B 고친 제목", "Bronze V")}
    assert by_ref["4A"]["platform"] == "codeforces"

    only_boj = db.get_problems_missing_statement("boj")
    assert {p["problem_ref"] for p in only_boj} == {"1000"}


def test_rows_with_statement_are_not_listed_or_overwritten():
    _seed("1000", statement="사용자가 직접 붙여 넣은 원문")
    _seed("2000")

    refs = {p["problem_ref"] for p in db.get_problems_missing_statement()}
    assert refs == {"2000"}, "이미 값이 있는 문제는 백필 대상이 아니다"

    # 값이 있는 행은 덮어쓰지 않는다 — 사용자 원문이 백필 값으로 날아가면 안 된다.
    assert db.set_problem_statement("boj", "1000", "백필로 넣으려는 값") == 0
    assert db.get_reviews_by_problem("boj", "1000")[0]["problem_statement"] == \
        "사용자가 직접 붙여 넣은 원문"


def test_set_problem_statement_fills_every_empty_row_of_the_problem(at_time):
    at_time("2024-01-01T00:00:00")
    _seed("1000")
    at_time("2024-01-02T00:00:00")
    _seed("1000")
    assert db.set_problem_statement("boj", "1000", "【문제】\n본문") == 2
    rows = db.get_reviews_by_problem("boj", "1000")
    assert all(r["problem_statement"] == "【문제】\n본문" for r in rows)


def test_set_problem_statement_rejects_empty():
    _seed("1000")
    assert db.set_problem_statement("boj", "1000", "") == 0
    assert db.get_reviews_by_problem("boj", "1000")[0]["problem_statement"] == ""


def test_resolve_statement_never_returns_failure_string(monkeypatch):
    """acmicpc.net 종료 이후 BOJ 리뷰가 프롬프트의 문제 설명 자리에 404 문자열을 넣고 있었다.

    수집 함수는 예외를 던지지 않고 실패 문자열을 반환하므로, 그걸 걸러 빈 본문을 줘야 한다
    (analyzer 는 제목·티어·태그·코드로 분석한다).
    """
    from routes import problem_resolve

    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: "크롤링 실패: 404 Client Error: Not Found for url: ...")
    assert problem_resolve.resolve_statement("boj", {"problem_ref": "1000"}) == ""

    monkeypatch.setattr(problem_resolve.api_client, "get_codeforces_problem_statement",
                        lambda ref: "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 "
                                    "제한적으로 분석합니다.")
    assert problem_resolve.resolve_statement("codeforces", {"problem_ref": "4A"}) == ""


def test_resolve_statement_prefers_stored_body_over_scraping(monkeypatch):
    """백필한 본문이 있으면 스크래핑을 타지 않는다 — BOJ 는 스크래핑이 죽어 이 경로가 유일하다."""
    from routes import problem_resolve

    monkeypatch.setattr(problem_resolve.api_client, "get_problem_statement",
                        lambda pid: pytest.fail("저장된 본문이 있으면 스크래핑하지 않는다"))
    stored = "【문제】\n두 정수 A와 B를 입력받아 A+B를 출력한다."
    assert problem_resolve.resolve_statement("boj", {"problem_ref": "1000"}, stored) == stored
