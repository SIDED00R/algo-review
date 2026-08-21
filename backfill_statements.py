"""기존 리뷰 기록의 problem_statement 를 백필한다.

`problem_statement` 는 PR #96 에서 추가돼 그 이후 제출한 건만 값이 있다. 그 전 기록을
남아 있는 소스에서 되살린다.

| 대상 | 소스 | 비고 |
|------|------|------|
| BOJ  | GitHub 저장소 README | acmicpc.net 이 종료돼 재수집이 불가하다. push 했던 문제만 복구된다 |
| CF   | codeforces.com 재수집 | 동작한다 |

사용자가 직접 붙여 넣었던 원문은 저장된 적이 없어 복구할 수 없다. 여기서 채우는 값은
"그 시절 스크래핑이 만들었을 본문"이다.

기본은 dry-run 이다. `--apply` 를 줘야 DB 에 쓴다.

    python backfill_statements.py                      # 전체 dry-run
    python backfill_statements.py --platform boj        # BOJ 만 dry-run
    python backfill_statements.py --apply               # 실제 기록
"""
import argparse
import re
import sys
import time

import clients as api_client
import db
from routes.helpers import build_solution_target
from routes.problem_resolve import is_scrape_failure

# CF 는 공격적인 스크래핑을 차단한다 — 문제 사이에 쉰다.
CF_DELAY_SEC = 1.5
# 이보다 짧으면 본문으로 보지 않는다. 실패 문자열은 is_scrape_failure 가 먼저 걸러내고,
# 이 길이 검사는 헤더만 남은 빈 README 같은 잔여 케이스를 막는다.
MIN_STATEMENT_LEN = 40

_SECTION_TO_LABEL = {"문제 설명": "문제", "입력": "입력", "출력": "출력"}


def parse_readme_sections(markdown: str) -> str:
    """build_readme 가 쓴 README 에서 문제 본문 섹션만 뽑아 BOJ 스크래핑과 같은 형태로 조립한다.

    build_readme 는 `## 문제 설명` / `## 입력` / `## 출력` 순으로 쓰고, 그 뒤에 리뷰 섹션이
    붙는다. 여기서는 위 세 개만 취해 `【문제】…【입력】…【출력】` 로 되돌린다 —
    get_problem_statement 가 만들던 형태와 같아야 저장된 값이 이질적으로 보이지 않는다.
    """
    parts = []
    # `## 제목` 으로 문서를 자른다. `#` 하나(문서 제목)와 `###` 이상은 건드리지 않는다.
    chunks = re.split(r"^##[ \t]+(.+?)[ \t]*$", markdown, flags=re.M)
    # chunks = [머리말, 제목1, 본문1, 제목2, 본문2, ...]
    for i in range(1, len(chunks) - 1, 2):
        label = _SECTION_TO_LABEL.get(chunks[i].strip())
        if not label:
            continue
        body = chunks[i + 1].strip()
        if body:
            parts.append(f"【{label}】\n{body}")
    return "\n\n".join(parts)


def fetch_boj_statement(problem: dict, repo: str, token: str) -> tuple[str, str]:
    """GitHub README 에서 BOJ 본문을 읽는다. (본문, 사유) 를 반환하고 실패 시 본문은 빈 문자열.

    폴더명은 `{번호}번. {제목}` 이라 제목에 의존한다. 회차 사이에 제목이 바뀐 문제는
    경로가 달라지므로 그 문제에 등장한 (제목, 티어명) 조합을 모두 시도한다.
    """
    tried = []
    for title, tier_name in problem["name_candidates"]:
        folder, _ = build_solution_target("boj", problem["problem_ref"], title, tier_name)
        path = f"{folder}/README.md"
        tried.append(path)
        try:
            markdown = api_client.get_raw_github_content(repo, path, token)
        except Exception:
            continue
        statement = parse_readme_sections(markdown)
        if statement:
            return statement, path
        return "", f"README 는 있으나 문제 설명 섹션이 비었다: {path}"
    return "", f"README 를 찾지 못했다 (시도: {', '.join(tried)})"


def reason_bucket(reason: str) -> str:
    """건너뛴 이유를 요약용 범주로 줄인다.

    상세 이유에는 경로가 붙어 있어 그대로 세면 항목이 전부 달라지고 요약이 의미를 잃는다.
    괄호·콜론 앞까지만 남긴다.
    """
    for sep in (" (", ": "):
        if sep in reason:
            return reason.split(sep, 1)[0]
    return reason


def fetch_cf_statement(problem: dict) -> tuple[str, str]:
    scraped = api_client.get_codeforces_problem_statement(problem["problem_ref"])
    if is_scrape_failure(scraped):
        return "", "codeforces.com 수집 실패"
    return scraped, "codeforces.com"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=["boj", "codeforces"],
                        help="지정하지 않으면 둘 다")
    parser.add_argument("--apply", action="store_true",
                        help="실제로 DB 에 쓴다. 없으면 dry-run")
    parser.add_argument("--limit", type=int, help="처리할 문제 수 상한(시험 실행용)")
    args = parser.parse_args()

    problems = db.get_problems_missing_statement(args.platform)
    if args.limit:
        problems = problems[:args.limit]
    if not problems:
        print("문제 설명이 빈 기록이 없습니다.")
        return 0

    repo = token = ""
    if any(p["platform"] == "boj" for p in problems):
        settings = db.get_github_settings() or {}
        repo = settings.get("target_repo") or ""
        token = settings.get("access_token") or ""
        if not (repo and token):
            print("경고: GitHub 연결·저장소가 없어 BOJ 는 건너뜁니다 "
                  "(acmicpc.net 종료로 README 가 유일한 소스입니다).\n")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] 대상 문제 {len(problems)}개"
          + (f" · GitHub {repo}" if repo else "") + "\n")

    filled = skipped = rows_written = 0
    reasons: dict[str, int] = {}

    for problem in problems:
        platform, ref = problem["platform"], problem["problem_ref"]
        label = f"{platform}/{ref}"

        if platform == "boj":
            if not (repo and token):
                statement, source = "", "GitHub 미연결"
            else:
                statement, source = fetch_boj_statement(problem, repo, token)
        else:
            statement, source = fetch_cf_statement(problem)
            time.sleep(CF_DELAY_SEC)

        # 실패 문자열을 저장하면 resolve_statement 가 그걸 무조건 우선하므로 그 문제의
        # 리뷰가 영구히 오염된다. 저장 직전에 한 번 더 막는다.
        if statement and (is_scrape_failure(statement) or len(statement) < MIN_STATEMENT_LEN):
            statement, source = "", f"본문이 너무 짧거나 실패 문자열({len(statement)}자)"

        if not statement:
            skipped += 1
            bucket = reason_bucket(source)
            reasons[bucket] = reasons.get(bucket, 0) + 1
            print(f"  SKIP  {label:24} {source}")
            continue

        filled += 1
        if args.apply:
            n = db.set_problem_statement(platform, ref, statement)
            rows_written += n
            print(f"  OK    {label:24} {len(statement):5}자 · 행 {n}개 · {source}")
        else:
            print(f"  OK    {label:24} {len(statement):5}자 · 행 {problem['empty_rows']}개 예정 · {source}")

    print(f"\n복구 가능 {filled}개 / 건너뜀 {skipped}개")
    if args.apply:
        print(f"갱신한 행 {rows_written}개")
    else:
        print("실제로 쓰려면 --apply 를 붙여 다시 실행하세요.")
    if reasons:
        print("\n건너뛴 이유:")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4}개  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
