"""백필 스크립트 검증.

README 파서는 두 형식을 되읽는다 — 이 앱의 `build_readme` 가 쓴 것과 BaekjoonHub 가 쓴 것.
전자는 build_readme 출력을 그대로 통과시켜 왕복을 고정하고, 후자는 실제 저장소에서 확인한
형태(### 헤더 · 헤더 뒤 공백 · HTML 본문)를 재현해 고정한다.
"""
import pytest

import backfill_statements as backfill
import clients.github as github_client
import db
from clients.github import _leading_problem_number
from routes.helpers import build_readme
from routes.problem_resolve import is_scrape_failure

# BaekjoonHub 는 폴더명의 공백을 U+2005(four-per-em space)로 바꾼다.
FOUR_PER_EM = " "


def _baekjoonhub_readme(title, number, description):
    """BaekjoonHub 가 쓰는 형태 — ### 헤더, 헤더 뒤 공백, 본문이 HTML."""
    return (
        "# [Silver II] {title} - {number} \n\n"
        "[문제 링크](https://www.acmicpc.net/problem/{number}) \n\n"
        "### 성능 요약\n\n메모리: 32412 KB, 시간: 6028 ms\n\n"
        "### 분류\n\n브루트포스 알고리즘\n\n"
        "### 제출 일자\n\n2026년 4월 11일 09:08:45\n\n"
        "### 문제 설명\n\n<p>{description}</p>\n\n"
        "### 입력 \n\n <p>첫째 줄에 N과 S가 주어진다. (1 ≤ N ≤ 20)</p>\n\n"
        "### 출력 \n\n <p>첫째 줄에 경우의 수를 출력한다.</p>\n"
    ).format(title=title, number=number, description=description)


# ── 파서 ──

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


def test_parses_baekjoonhub_readme_with_html_body():
    """저장소의 백준 README 는 대부분 BaekjoonHub 가 쓴 것이다 — ### + HTML 을 받아야 한다."""
    readme = _baekjoonhub_readme(
        "부분수열의 합", 1182, "N개의 정수로 이루어진 수열에서 합이 S가 되는 경우의 수를 구하시오.")
    statement = backfill.parse_readme_sections(readme)

    assert statement.startswith("【문제】")
    assert "【입력】" in statement and "【출력】" in statement
    assert "합이 S가 되는 경우의 수" in statement
    assert "<p>" not in statement, "HTML 태그를 벗겨야 한다"
    assert "성능 요약" not in statement
    assert "브루트포스" not in statement
    assert "32412" not in statement


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


# ── 저장소 조회 ──

def test_leading_problem_number_accepts_both_folder_formats():
    """BaekjoonHub 는 `1182. 제목`, 이 앱은 `1182번. 제목` 으로 쓴다 — 둘 다 받아야 한다."""
    assert _leading_problem_number("1182." + FOUR_PER_EM + "부분수열의" + FOUR_PER_EM + "합") == 1182
    assert _leading_problem_number("1182번. 부분수열의 합") == 1182
    assert _leading_problem_number("31429." + FOUR_PER_EM + "SUAPC") == 31429


def test_leading_problem_number_requires_a_number_boundary():
    """숫자로 시작하기만 하면 받으면 문제 폴더가 아닌 것을 문제로 오인한다.

    숫자 뒤에 `.` 또는 `번.` 이 와야 한다 — 이걸 빼면 `2024 대회 후기` 가 2024번 문제가 된다.
    """
    assert _leading_problem_number("2024 대회 후기") is None
    assert _leading_problem_number("2024년 정리") is None
    assert _leading_problem_number("제목만 있는 폴더") is None


def test_fetch_boj_statement_uses_tree_path(monkeypatch):
    """경로를 조립하지 않는다 — BaekjoonHub 는 공백을 U+2005 로, 특수문자를 전각으로 바꾸고
    `번` 을 붙이지 않으며, 티어 폴더도 DB 값과 다를 수 있다."""
    asked = []
    bh_path = "백준/Silver/1182." + FOUR_PER_EM + "부분수열의" + FOUR_PER_EM + "합/README.md"

    def fake_get(repo, path, token=None):
        asked.append((repo, path, token))
        return _baekjoonhub_readme("부분수열의 합", 1182, "합이 S가 되는 경우의 수를 구하시오.")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    statement, source = backfill.fetch_boj_statement(
        {"problem_ref": "1182"}, "me/solutions", "tok", {1182: [bh_path]})

    assert asked == [("me/solutions", bh_path, "tok")]
    assert statement.startswith("【문제】")
    assert source == bh_path


def test_fetch_boj_statement_tries_next_candidate_when_first_has_no_body(monkeypatch):
    """같은 문제에 폴더가 둘 있을 수 있다(앱이 올린 것 + BaekjoonHub 것) — 본문이 나오는 것을 쓴다."""
    empty = "백준/Unrated/1182번. 부분수열의 합/README.md"
    good = "백준/Silver/1182." + FOUR_PER_EM + "부분수열의" + FOUR_PER_EM + "합/README.md"

    def fake_get(repo, path, token=None):
        if path == empty:
            return build_readme(problem_ref="1182", title="부분수열의 합", tier_name="Unrated",
                                tags=[], language="Python 3", url="https://boj.kr/1182")
        return _baekjoonhub_readme("부분수열의 합", 1182, "합이 S가 되는 경우의 수를 구하시오.")

    monkeypatch.setattr(backfill.api_client, "get_raw_github_content", fake_get)
    statement, source = backfill.fetch_boj_statement(
        {"problem_ref": "1182"}, "me/solutions", "tok", {1182: [empty, good]})
    assert statement.startswith("【문제】")
    assert source == good


def test_fetch_boj_statement_reports_when_repo_has_no_readme(monkeypatch):
    monkeypatch.setattr(backfill.api_client, "get_raw_github_content",
                        lambda *a, **k: pytest.fail("후보가 없으면 요청하지 않는다"))
    statement, source = backfill.fetch_boj_statement(
        {"problem_ref": "1182"}, "me/solutions", "tok", {})
    assert statement == ""
    assert source == "저장소에 README 가 없다"


def test_fetch_boj_statement_reports_when_readme_lacks_sections(monkeypatch):
    """본문 없이 올라간 README — 조용히 빈 값을 저장하지 않고 이유를 보고해야 한다."""
    path = "백준/Unrated/1182번. 부분수열의 합/README.md"
    monkeypatch.setattr(backfill.api_client, "get_raw_github_content",
                        lambda repo, p, token=None: build_readme(
                            problem_ref="1182", title="부분수열의 합", tier_name="Unrated",
                            tags=[], language="Python 3", url="https://boj.kr/1182"))
    statement, source = backfill.fetch_boj_statement(
        {"problem_ref": "1182"}, "me/solutions", "tok", {1182: [path]})
    assert statement == ""
    assert "문제 설명 섹션이 비었다" in source


def test_reason_bucket_collapses_paths_for_the_summary():
    """이유마다 경로가 붙으면 요약이 전부 다른 항목이 되어 의미를 잃는다."""
    a = "README 는 있으나 문제 설명 섹션이 비었다: 백준/Gold/1654번. 랜선 자르기/README.md"
    b = "README 는 있으나 문제 설명 섹션이 비었다: 백준/Silver/1003번. 피보나치 함수/README.md"
    assert backfill.reason_bucket(a) == backfill.reason_bucket(b) == \
        "README 는 있으나 문제 설명 섹션이 비었다"
    assert backfill.reason_bucket("저장소에 README 가 없다") == "저장소에 README 가 없다"


# ── 저장 가드 ──

def test_scrape_failure_strings_are_rejected():
    """수집 함수는 예외 대신 실패 문자열을 반환한다 — 저장하면 리뷰가 영구히 오염된다."""
    assert is_scrape_failure("크롤링 실패: 404 Client Error: Not Found for url: ...")
    assert is_scrape_failure("문제 설명을 가져올 수 없습니다.")
    assert is_scrape_failure("문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 "
                             "제한적으로 분석합니다.")
    assert is_scrape_failure("")
    assert is_scrape_failure("   ")
    assert not is_scrape_failure("【문제】\n두 정수 A와 B를 입력받아 A+B를 출력한다.")


def _seed(problem_ref, platform="boj", title="A+B", tier_name="Bronze V", statement=""):
    db.save_review(problem_id=int(problem_ref) if problem_ref.isdigit() else 0,
                   title=title, tier=1, tags=["수학"], code="print(1)", feedback="f",
                   efficiency="good", platform=platform, problem_ref=problem_ref,
                   tier_name=tier_name, language="Python 3", problem_statement=statement)


def test_missing_statement_groups_by_problem(at_time):
    at_time("2024-01-01T00:00:00")
    _seed("1000", title="A+B")
    at_time("2024-01-02T00:00:00")
    _seed("1000", title="A+B 고친 제목")
    _seed("4A", platform="codeforces", title="Watermelon", tier_name="Codeforces 800")

    problems = db.get_problems_missing_statement()
    by_ref = {p["problem_ref"]: p for p in problems}
    assert by_ref["1000"]["empty_rows"] == 2
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


# ── 수집 실패 처리 ──

def test_resolve_statement_never_returns_failure_string(monkeypatch):
    """acmicpc.net 종료 이후 BOJ 리뷰가 프롬프트의 문제 설명 자리에 404 문자열을 넣고 있었다."""
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


# ── 저장소 트리 조회 (#100 의 핵심 함수 — 예전에는 커버리지 0 이었다) ──

def test_readme_paths_are_found_by_number_not_by_path_assembly(monkeypatch):
    """트리 → {문제번호: [README 경로]} 변환. BaekjoonHub 폴더명 규칙을 실제로 통과시킨다.

    폴더명을 조립해 맞히려 하면 실패한다 — BaekjoonHub 는 공백을 U+2005 로, 특수문자를
    전각으로 바꾸고 `번` 을 붙이지 않으며, 티어 폴더도 저장 당시 값이라 DB 와 다를 수 있다.
    예전 테스트는 이 dict 를 리터럴로 주입해서, 이 함수가 {} 를 돌려줘도 전부 초록이었다.
    """
    tree = [
        # BaekjoonHub: `번` 없음 + U+2005 공백 + 전각 문자
        {"type": "blob", "path": "백준/Silver/1182." + FOUR_PER_EM + "부분수열의 합/README.md"},
        {"type": "blob", "path": "백준/Silver/1182." + FOUR_PER_EM + "부분수열의 합/solution.py"},
        # 이 앱이 올린 폴더: `번.` 형태. 같은 문제에 폴더가 둘일 수 있다
        {"type": "blob", "path": "백준/Gold/1182번. 부분수열의 합/README.md"},
        # 영문 루트도 받는다
        {"type": "blob", "path": "boj/Bronze/1000. A＋B/README.md"},
        # 번호 경계 — `.` 이 없으면 문제 폴더가 아니다
        {"type": "blob", "path": "백준/Gold/2024 대회 후기/README.md"},
        # 깊이가 4 가 아닌 항목은 제외. `.../sub/README.md` 는 parts[3]=="sub" 라
        # README 위치 규칙에 먼저 걸리므로, 깊이만이 이유인 경로를 따로 둔다.
        {"type": "blob", "path": "백준/Gold/9999. 제목/README.md/x"},
        {"type": "blob", "path": "백준/Gold/9998. 제목/sub/README.md"},
        {"type": "blob", "path": "백준/README.md"},
        # BOJ 루트가 아닌 것은 제외. 번호 파싱이 **성공하는** 폴더명을 써야 루트 필터를
        # 실제로 검증한다 — `4A. Watermelon` 은 번호 경계 규칙에 먼저 걸려(4 뒤에 A)
        # 루트 필터를 지워도 결과가 같았다(거짓 초록).
        {"type": "blob", "path": "Codeforces/Div2/777. Watermelon/README.md"},
        # blob 이 아닌 항목은 제외
        {"type": "tree", "path": "백준/Gold/8888. 제목/README.md"},
    ]
    monkeypatch.setattr(github_client, "fetch_repo_tree", lambda repo, token=None: tree)

    paths = github_client.get_boj_readme_paths("me/solutions", "tok")

    assert sorted(paths) == [1000, 1182]
    assert len(paths[1182]) == 2  # 두 폴더 모두 후보로 돌려준다
    assert all(p.endswith("README.md") for refs in paths.values() for p in refs)
    assert 2024 not in paths   # `2024 대회 후기`
    assert 9999 not in paths   # 깊이 5 (parts[3]=="README.md" 인데 길이가 5)
    assert 9998 not in paths   # README 가 문제 폴더 직하위가 아니다
    assert 8888 not in paths   # tree
    assert 777 not in paths    # BOJ 루트가 아니다


def test_truncated_tree_raises_instead_of_returning_partial_results():
    """GitHub 가 트리를 자르면(truncated) 부분 결과를 성공으로 취급하면 안 된다 —
    가져오기·백필이 조용히 일부 문제를 누락한다."""
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tree": [{"type": "blob", "path": "백준/Gold/1000. A+B/README.md"}],
                    "truncated": True}

    import clients.github as gh
    original = gh.requests.get
    gh.requests.get = lambda *a, **k: _Resp()
    try:
        with pytest.raises(ValueError, match="잘렸"):
            gh.fetch_repo_tree("me/solutions", "tok")
    finally:
        gh.requests.get = original


# ── main() 의 저장 가드 (회귀) ──
#
# "저장 가드" 섹션이 is_scrape_failure 와 set_problem_statement 만 검사해, main() 안의
# 길이 검사(MIN_STATEMENT_LEN)는 0 으로 바꿔도 스위트가 초록이었다.

def _run_main(monkeypatch, statement, apply=False):
    """main() 을 BOJ 한 건에 대해 돌린다. 수집 결과만 주입한다."""
    monkeypatch.setattr(db, "get_problems_missing_statement",
                        lambda platform=None: [{"platform": "boj", "problem_ref": "1000",
                                                "empty_rows": 1}])
    monkeypatch.setattr(db, "get_github_settings",
                        lambda: {"target_repo": "me/solutions", "access_token": "tok"})
    monkeypatch.setattr(backfill.api_client, "get_boj_readme_paths",
                        lambda repo, token=None: {1000: ["백준/Silver/1000. A+B/README.md"]})
    monkeypatch.setattr(backfill, "fetch_boj_statement",
                        lambda problem, repo, token, paths: (statement, "테스트"))
    written = []
    monkeypatch.setattr(db, "set_problem_statement",
                        lambda p, r, s: written.append((p, r, s)) or 1)
    argv = ["backfill_statements.py"] + (["--apply"] if apply else [])
    monkeypatch.setattr(backfill.sys, "argv", argv)
    assert backfill.main() == 0
    return written


def test_short_statement_is_skipped_not_stored(monkeypatch, capsys):
    short = "가" * (backfill.MIN_STATEMENT_LEN - 1)
    written = _run_main(monkeypatch, short, apply=True)

    assert written == []
    out = capsys.readouterr().out
    assert "SKIP" in out and "너무 짧거나" in out


def test_long_enough_statement_is_stored(monkeypatch):
    body = "가" * (backfill.MIN_STATEMENT_LEN + 1)
    written = _run_main(monkeypatch, body, apply=True)

    assert len(written) == 1 and written[0][2] == body


def test_failure_string_is_skipped_even_when_long(monkeypatch):
    """길이는 충분하지만 실패 문자열이면 저장하면 안 된다 — 저장하면 그 문제의 리뷰가
    resolve_statement 를 통해 영구히 오염된다."""
    failure = "크롤링 실패: 404 Client Error: Not Found for url: " + "x" * 40
    assert len(failure) >= backfill.MIN_STATEMENT_LEN
    written = _run_main(monkeypatch, failure, apply=True)

    assert written == []


def test_dry_run_never_writes(monkeypatch, capsys):
    body = "가" * (backfill.MIN_STATEMENT_LEN + 1)
    written = _run_main(monkeypatch, body, apply=False)

    assert written == []
    assert "--apply" in capsys.readouterr().out


def test_db_target_is_printed_before_any_query(monkeypatch, capsys):
    """어느 DB 에 쓰는지 먼저 찍어야 한다 — config 의 env_file 은 CWD 상대 경로라
    리포 루트가 아닌 곳에서 돌리면 조용히 로컬 SQLite 에 붙고 '대상 0건 + exit 0' 이 된다."""
    monkeypatch.setattr(db, "get_problems_missing_statement", lambda platform=None: [])
    monkeypatch.setattr(backfill.sys, "argv", ["backfill_statements.py"])

    assert backfill.main() == 0
    out = capsys.readouterr().out
    assert "sqlite" in out or "postgres" in out
    assert out.index("DRY-RUN") < out.index("문제 설명이 빈 기록이 없습니다")


def test_reason_bucket_collapses_every_form_main_produces():
    """main() 이 실제로 만드는 사유 전부가 수렴해야 한다.

    예전에는 `문자열(37자)` 처럼 괄호 앞에 공백이 없어 길이마다 별개 버킷이 됐고,
    구분자 `" ("` 는 어떤 사유에도 매칭되지 않는 dead branch 였다.
    """
    forms = [
        "BOJ 문제 번호가 숫자가 아니다",
        "저장소에 README 가 없다",
        "README 는 있으나 문제 설명 섹션이 비었다: 백준/Gold/1182. 제목/README.md",
        "codeforces.com 수집 실패",
        "GitHub 미연결",
        "저장소에 BOJ README 가 없다",
        "처리 중 예외: ValueError",
        "본문이 너무 짧거나 실패 문자열 (37자)",
        "본문이 너무 짧거나 실패 문자열 (12자)",
    ]
    buckets = [backfill.reason_bucket(f) for f in forms]
    # 길이만 다른 두 사유가 하나로 합쳐진다.
    assert len(set(buckets)) == len(forms) - 1
    assert buckets[-1] == buckets[-2] == "본문이 너무 짧거나 실패 문자열"
    assert buckets[2] == "README 는 있으나 문제 설명 섹션이 비었다"
    assert buckets[6] == "처리 중 예외"
    # 경로·상세가 붙지 않는 사유는 그대로 남는다.
    assert buckets[0] == forms[0]
