"""기존 리뷰 기록의 problem_statement 를 백필한다.

소스: BOJ 는 GitHub 저장소 README(acmicpc.net 종료로 재수집 불가 — push 한 문제만),
CF 는 codeforces.com 재수집.

기본은 dry-run 이다. `--apply` 를 줘야 DB 에 쓴다.

    python backfill_statements.py                      # 전체 dry-run
    python backfill_statements.py --platform boj        # BOJ 만 dry-run
    python backfill_statements.py --apply               # 실제 기록
"""
import argparse
import re
import sys
import time

from bs4 import BeautifulSoup

import clients as api_client
import db
from config import Settings
from routes.problem_resolve import is_scrape_failure

# CF 는 공격적인 스크래핑을 차단한다 — 문제 사이에 쉰다.
CF_DELAY_SEC = 1.5
# 이보다 짧으면 본문으로 보지 않는다. 실패 문자열은 is_scrape_failure 가 먼저 걸러내고,
# 이 길이 검사는 본문이 한두 줄뿐인 README 같은 잔여 케이스를 막는다.
MIN_STATEMENT_LEN = 40

_SECTION_TO_LABEL = {"문제 설명": "문제", "입력": "입력", "출력": "출력"}


def _plain_text(markup: str) -> str:
    """BaekjoonHub README 는 본문을 HTML(`<p>`, `<sup>` …)로 담는다 — 태그를 벗긴다.

    이 앱의 build_readme 가 쓴 본문에는 태그가 없다.
    """
    if "<" not in markup:
        return markup.strip()
    return BeautifulSoup(markup, "html.parser").get_text(separator="\n", strip=True)


def parse_readme_sections(markdown: str) -> str:
    """README 에서 문제 본문 섹션만 뽑아 BOJ 스크래핑과 같은 형태로 조립한다.

    두 형식을 받는다.
    - 이 앱의 `build_readme`: `## 문제 설명` / `## 입력` / `## 출력`, 태그 없음
    - BaekjoonHub: `### 문제 설명` / `### 입력 ` / `### 출력 `, 본문이 HTML, 헤더 뒤 공백 있음

    `【문제】…【입력】…【출력】` 형태로 되돌린다 — get_problem_statement 가 만드는 형태와 같다.
    리뷰 섹션·머리말은 라벨 화이트리스트로 걸러진다.
    """
    parts = []
    # `##` 또는 `###` 헤더로 자른다. `#` 하나(문서 제목)는 건드리지 않는다.
    chunks = re.split(r"^#{2,3}[ \t]+(.+?)[ \t]*$", markdown, flags=re.M)
    # chunks = [머리말, 제목1, 본문1, 제목2, 본문2, ...]
    for i in range(1, len(chunks) - 1, 2):
        label = _SECTION_TO_LABEL.get(chunks[i].strip())
        if not label:
            continue
        body = _plain_text(chunks[i + 1])
        if body:
            parts.append("【" + label + "】\n" + body)
    return "\n\n".join(parts)


def reason_bucket(reason: str) -> str:
    """건너뛴 이유를 요약용 범주로 줄인다.

    괄호·콜론 앞까지만 남긴다.
    """
    for sep in (" (", ": "):
        if sep in reason:
            return reason.split(sep, 1)[0]
    return reason


def fetch_boj_statement(problem: dict, repo: str, token: str,
                        readme_paths: dict[int, list[str]]) -> tuple[str, str]:
    """GitHub README 에서 BOJ 본문을 읽는다. (본문, 사유) 를 반환하고 실패 시 본문은 빈 문자열.

    BaekjoonHub 경로는 공백을 U+2005 로, 특수문자를 전각으로 바꾸고 `번` 을 붙이지 않으며,
    티어 폴더도 저장 당시 값이라 DB 와 다를 수 있다. 번호로 트리에서 찾는다. 같은 문제에
    폴더가 둘 있을 수 있고(앱이 올린 것 + BaekjoonHub 것) 본문이 나오는 첫 번째를 쓴다.
    """
    try:
        problem_id = int(problem["problem_ref"])
    except (TypeError, ValueError):
        return "", "BOJ 문제 번호가 숫자가 아니다"

    candidates = readme_paths.get(problem_id, [])
    if not candidates:
        return "", "저장소에 README 가 없다"

    for path in candidates:
        try:
            markdown = api_client.get_raw_github_content(repo, path, token)
        except Exception:
            continue
        statement = parse_readme_sections(markdown)
        if statement:
            return statement, path
    return "", "README 는 있으나 문제 설명 섹션이 비었다: " + candidates[0]


def fetch_cf_statement(problem: dict) -> tuple[str, str]:
    scraped = api_client.get_codeforces_problem_statement(problem["problem_ref"])
    if is_scrape_failure(scraped):
        return "", "codeforces.com 수집 실패"
    return scraped, "codeforces.com"


def db_target_label() -> str:
    """접속 대상 DB 를 비밀 없이 한 줄로 표기한다."""
    from sqlalchemy import make_url  # db/connection.py 와 같은 경로로 맞춘다
    try:
        return make_url(Settings().sqlalchemy_url).render_as_string(hide_password=True)
    except Exception as e:
        return "DB 대상 판별 실패: " + str(e)


def main() -> int:
    # 출력에 cp949 로 인코딩할 수 없는 문자(em dash 등)가 있다.
    # Windows 콘솔 기본 코드페이지는 cp949 다.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=["boj", "codeforces"],
                        help="지정하지 않으면 둘 다")
    parser.add_argument("--apply", action="store_true",
                        help="실제로 DB 에 쓴다. 없으면 dry-run")
    parser.add_argument("--limit", type=int, help="처리할 문제 수 상한(시험 실행용)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    # 접속 대상을 가장 먼저 찍는다 — config 의 env_file 은 CWD 상대 경로라, 리포 루트가
    # 아닌 곳에서 돌리면 조용히 로컬 SQLite 로 붙는다.
    print("[" + mode + "] " + db_target_label())

    problems = db.get_problems_missing_statement(args.platform)
    if args.limit is not None:
        problems = problems[:args.limit]
    if not problems:
        print("문제 설명이 빈 기록이 없습니다.")
        return 0

    repo = token = ""
    readme_paths: dict[int, list[str]] = {}
    if any(p["platform"] == "boj" for p in problems):
        gh_settings = db.get_github_settings() or {}
        repo = gh_settings.get("target_repo") or ""
        token = gh_settings.get("access_token") or ""
        if not (repo and token):
            print("경고: GitHub 연결·저장소가 없어 BOJ 는 건너뜁니다 "
                  "(acmicpc.net 종료로 README 가 유일한 소스입니다).\n")
        else:
            # 트리는 한 번만 받는다. 폴더명 규칙이 문제마다 달라 개별 경로 요청은
            # 대부분 404 가 된다.
            try:
                readme_paths = api_client.get_boj_readme_paths(repo, token)
                print("저장소 BOJ README " + str(len(readme_paths)) + "개 확인\n")
            except Exception as e:
                print("경고: 저장소 트리를 받지 못했습니다 (" + str(e) + ") — BOJ 는 건너뜁니다.\n")

    print("[" + mode + "] 대상 문제 " + str(len(problems)) + "개"
          + (" · GitHub " + repo if repo else "") + "\n")

    filled = skipped = rows_written = 0
    reasons: dict[str, int] = {}

    for problem in problems:
        platform, ref = problem["platform"], problem["problem_ref"]
        label = platform + "/" + ref

        # 문제 단위로 HTTP 수집·파싱 예외를 잡아 SKIP 사유로 집계한다.
        # DB 쓰기 실패는 여기서 잡지 않고 스크립트를 중단시킨다.
        try:
            if platform == "boj":
                if not (repo and token):
                    statement, source = "", "GitHub 미연결"
                elif not readme_paths:
                    statement, source = "", "저장소에 BOJ README 가 없다"
                else:
                    statement, source = fetch_boj_statement(problem, repo, token, readme_paths)
            else:
                statement, source = fetch_cf_statement(problem)
                time.sleep(CF_DELAY_SEC)
        except Exception as e:
            statement, source = "", "처리 중 예외: " + type(e).__name__

        # resolve_statement 는 저장된 값이 있으면 무조건 그것을 우선한다.
        # 저장 직전에 한 번 더 막는다.
        if statement and (is_scrape_failure(statement) or len(statement) < MIN_STATEMENT_LEN):
            source = "본문이 너무 짧거나 실패 문자열 (" + str(len(statement)) + "자)"
            statement = ""

        if not statement:
            skipped += 1
            bucket = reason_bucket(source)
            reasons[bucket] = reasons.get(bucket, 0) + 1
            print("  SKIP  " + label.ljust(24) + " " + source)
            continue

        filled += 1
        if args.apply:
            n = db.set_problem_statement(platform, ref, statement)
            rows_written += n
            print("  OK    " + label.ljust(24) + " " + str(len(statement)).rjust(5)
                  + "자 · 행 " + str(n) + "개 · " + source)
        else:
            print("  OK    " + label.ljust(24) + " " + str(len(statement)).rjust(5)
                  + "자 · 행 " + str(problem["empty_rows"]) + "개 예정 · " + source)

    print("\n복구 가능 " + str(filled) + "개 / 건너뜀 " + str(skipped) + "개")
    if args.apply:
        print("갱신한 행 " + str(rows_written) + "개")
    else:
        print("실제로 쓰려면 --apply 를 붙여 다시 실행하세요.")
    if reasons:
        print("\n건너뛴 이유:")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print("  " + str(count).rjust(4) + "개  " + reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
