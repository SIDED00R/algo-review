"""GitHub push 공용 헬퍼 — README 조립, 저장 폴더/커밋 메시지, 저장소 타깃 병합, 파일 push.

push 함수가 둘인 이유: push_solution 은 파일별 PUT(가져오기처럼 수백 건을 훑는 경로에서
한 문제가 실패해도 나머지가 진행되어야 한다), push_review_bundle 은 README+코드를
한 커밋으로 묶는다(단건 등록은 저장소 이력이 문제 단위로 남는 게 낫다).
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import db
import clients as api_client
from routes.models import validate_platform

logger = logging.getLogger("uvicorn.error")

KST = timezone(timedelta(hours=9))


def push_solution(repo: str, token: str, folder: str, file_stem: str,
                  ext: str, code: str, readme: str, msg: str) -> bool:
    """README + 코드 파일을 저장소에 push. 코드 push 성공 여부 반환."""
    readme_ok = api_client.push_file_to_github(repo, token, f"{folder}/README.md", readme, msg)
    code_ok = api_client.push_file_to_github(repo, token, f"{folder}/{file_stem}{ext}", code, msg)
    if code_ok and not readme_ok:
        # README 만 실패하면 호출부가 성공으로 집계해 사용자에게 보고되는 숫자가 틀린다.
        logger.warning("README push 실패 (repo=%s, folder=%s) — 코드만 올라갔다", repo, folder)
    return code_ok and readme_ok


def upstream_failure(action: str, exc: Exception) -> HTTPException:
    """예외 원문을 응답에 싣지 않는다 — 타입명만 노출하고 세부는 로그로 보낸다.

    openai SDK 의 `APIStatusError` 메시지는 `Error code: 401 - {제공자 응답 본문}` 형태로
    **제공자 본문을 그대로** 싣는다(실측). `.env.example` 이 OpenAI 호환 서드파티
    엔드포인트를 1급 대안으로 안내하므로 그 본문 형태를 통제할 수 없고, `base_url` 이
    내부 프록시면 그 주소도 함께 나간다. clients.codeforces 의 자격증명 유출과 같은 계열이다.
    """
    logger.exception("%s", action)
    return HTTPException(status_code=502, detail=f"{action} ({type(exc).__name__})")


def require_platform(value: str) -> str:
    """플랫폼 문자열을 검증해 400 으로 바꾼다.

    validate_platform 은 pydantic 검증용이라 ValueError 를 던진다 — 라우터에서 그대로
    쓰면 500 이 된다. 네 라우터가 같은 try/except 를 복제하고 있었고, 그중 solved.py 는
    아예 검증하지 않았다.
    """
    try:
        return validate_platform(value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def require_language(language: str) -> str:
    """제출 언어를 강제한다. 세 엔드포인트(/api/review, /api/review/pending,
    /api/push-review)가 공유하는 하류 제약이라 규칙을 한 곳에 둔다.

    언어를 모르면 get_file_extension 이 `.txt` 를 주고, 저장소에 `1000.txt` 로 커밋된
    풀이는 rereview 가 "저장된 언어 정보가 없어 파일명을 재현할 수 없습니다" 로 **영구
    거부**한다. 프론트의 "자동 감지" 는 detectLanguage 가 미인식 코드에 '' 를 반환하므로
    빈 값이 실제로 도달한다.
    """
    value = (language or "").strip()
    if not value:
        raise HTTPException(status_code=400,
                            detail="언어를 선택해주세요. 파일 확장자를 정하는 데 필요합니다.")
    return value


def build_solution_target(platform: str, problem_ref, title: str, tier_name: str = "") -> tuple[str, str]:
    """플랫폼별 저장소 폴더명과 커밋 메시지를 조립해 (folder, msg) 반환."""
    if platform == "boj":
        # `" "` 는 truthy 지만 split() 이 [] 라 인덱싱이 IndexError 였다.
        tier_cat = (tier_name.split() or ["Unrated"])[0]
        folder = f"백준/{tier_cat}/{problem_ref}번. {title}"
        msg = f"[BOJ] {problem_ref}번. {title}"
    else:
        folder = f"Codeforces/{problem_ref}. {title}"
        msg = f"[Codeforces] {problem_ref}. {title}"
    return folder, msg


def merged_github_target(repo_override: str = "", token_override: str = "") -> tuple[str, str]:
    """override 우선으로 GitHub 저장소/토큰을 병합, 둘 다 없으면 ("", "") 반환."""
    gh_settings = db.get_github_settings()
    github_repo = (repo_override or "").strip() or (gh_settings["target_repo"] if gh_settings else "")
    github_token = (token_override or "").strip() or (gh_settings["access_token"] if gh_settings else "")
    return github_repo, github_token


_EFFICIENCY_LABELS = {"good": "효율적", "ok": "보통", "poor": "비효율적"}


def _review_section_lines(review: dict) -> list[str]:
    """README 의 '## 코드 리뷰' 섹션 줄 목록. 리뷰 대기 행이면 안내 한 줄만 넣는다."""
    lines = ["", "## 코드 리뷰", ""]
    if review.get("efficiency") == db.PENDING_EFFICIENCY:
        return lines + ["⏳ AI 리뷰 대기 중 — 앱에서 리뷰를 실행하면 이 문서가 갱신됩니다."]

    lines.append(f"- 효율성: {_EFFICIENCY_LABELS.get(review.get('efficiency'), '-')}")
    if review.get("complexity"):
        lines.append(f"- 시간복잡도: {review['complexity']}")
    if review.get("better_algorithm"):
        lines.append(f"- 더 나은 알고리즘: {review['better_algorithm']}")
    for label, key in (("잘한 점", "strengths"), ("개선할 점", "weaknesses")):
        items = review.get(key) or []
        if items:
            lines += ["", f"### {label}", ""] + [f"- {item}" for item in items]
    if review.get("feedback"):
        lines += ["", "### 상세 피드백", "", review["feedback"]]
    return lines


def _readme_exists(repo: str, token: str, folder: str) -> bool:
    """저장소에 이 문제의 README 가 이미 있는지. 조회 실패는 "있다" 로 본다 —
    확실하지 않을 때 덮어쓰는 쪽으로 기울면 지켜야 할 문서를 지울 수 있다."""
    try:
        return api_client.get_github_file_sha(repo, f"{folder}/README.md", token) is not None
    except Exception as e:
        logger.warning("README 존재 확인 실패 (repo=%s, folder=%s) — 보수적으로 '있다'로 본다: %s",
                       repo, folder, e)
        return True


def push_review_bundle(repo: str, token: str, *, platform: str, problem_ref: str, title: str,
                       tier_name: str, tags: list, language: str, code: str, url: str = "",
                       review: dict | None = None, description: str = "",
                       input_desc: str = "", output_desc: str = "",
                       submitted_at: str = "", require_sections: bool = True) -> str:
    """README + 코드 파일을 저장소에 push 하고 폴더 경로를 반환한다. 실패 시 HTTPException(500).

    description 이 비어 있으면 플랫폼별 문제 본문을 자동 수집한다 — LLM 이 아니라 스크래핑이라
    리뷰 없이 올리는 경로에서도 그대로 동작한다.

    require_sections: 스크래핑 실패 시 막을지 여부. 기존 문서를 본문 없이 재생성하면
    이미 올라간 문제 설명을 지우므로 True(기본값)로 막는다. 단 **저장소에 그 README 가
    실제로 있을 때만** 막는다 — 지킬 문서가 없으면 502 는 최초 등록을 이유 없이 차단한다
    (acmicpc.net 종료로 BOJ 수집이 상시 실패하므로 BOJ push 가 전부 막혀 있었다).
    False 로 넘기면 확인조차 하지 않는다(이미 문서가 없음이 확실한 경로).

    description 을 직접 주면 input/output 은 호출자 책임이다. `【문제】/【입력】/【출력】`
    마커가 들어 있으면 build_readme 가 세 섹션으로 되쪼갠다.
    """
    ext = api_client.get_file_extension(language)
    url = url or api_client.get_problem_url(platform, problem_ref)
    folder, msg = build_solution_target(platform, problem_ref, title, tier_name)

    # 호출자가 섹션을 하나라도 직접 줬으면 스크래핑하지 않는다 — 예전에는 description 만
    # 보고 분기해서, description="" + input_desc/output_desc 조합에서 호출자가 넘긴 값을
    # 스크래핑 결과로 덮어썼다(CF 뷰어에서 넘어오는 경로가 그 조합을 만든다).
    if not (description or input_desc or output_desc):
        if platform == "boj":
            try:
                boj_problem_id = int(problem_ref)
            except ValueError:
                raise HTTPException(status_code=400, detail="BOJ 문제 번호는 숫자여야 합니다.")
            sections = api_client.get_boj_problem_sections(boj_problem_id)
        else:
            sections = api_client.get_cf_problem_sections(problem_ref)
        if not sections or not any(sections.values()):
            # 스크래핑 실패를 빈 섹션으로 오인하면 README 를 본문 없이 재생성해 이미 잘
            # 올라가 있던 문제 설명을 지워버린다. None 뿐 아니라 "200 인데 본문이 비었다"도
            # 실패로 본다(수집기가 실패를 어떻게 표현하든 결과가 같아야 한다).
            #
            # 다만 무조건 막으면 안 된다 — 지킬 문서가 없는데 502 를 내면 최초 등록이
            # 이유 없이 차단된다. acmicpc.net 종료로 BOJ 수집이 상시 실패하므로 실제로
            # BOJ 의 "GitHub에 올리기" 가 전부 502 였고, 메시지("잠시 후 다시 시도")는
            # 절대 성공하지 않는 재시도를 유도했다.
            if require_sections and _readme_exists(repo, token, folder):
                raise HTTPException(
                    status_code=502,
                    detail="문제 본문을 불러오지 못해 기존 README 를 덮어쓰지 않았습니다. "
                           "문제 설명을 직접 붙여 넣은 뒤 다시 올려주세요.")
            # 지킬 기존 문서가 없다 — 본문 없이 진행한다.
            sections = {}
        description = sections.get("description", "")
        input_desc = sections.get("input", "")
        output_desc = sections.get("output", "")

    readme = build_readme(problem_ref, title, tier_name, tags, language, url,
                          description, input_desc, output_desc, review, submitted_at)
    ok = api_client.push_files_to_github(repo, token, [
        {"path": f"{folder}/README.md", "content": readme},
        {"path": f"{folder}/{problem_ref}{ext}", "content": code},
    ], msg)
    if not ok:
        raise HTTPException(status_code=500, detail="GitHub push에 실패했습니다.")
    return folder


def require_github_target() -> tuple[str, str]:
    """연결된 저장소/토큰을 반환한다. 미연결·미선택이면 400 으로 안내한다."""
    github_repo, github_token = merged_github_target()
    if not github_token:
        raise HTTPException(status_code=400,
                            detail="GitHub 연결이 필요합니다. 헤더의 '🐙 GitHub 연결' 버튼을 눌러주세요.")
    if not github_repo:
        raise HTTPException(status_code=400, detail="GitHub 저장소를 선택해주세요.")
    return github_repo, github_token


def _submitted_at_str(submitted_at: str) -> str:
    """'제출 일자' 표기. 재업로드는 원래 제출 시각을 그대로 써야 앱 기록과 어긋나지 않는다."""
    if submitted_at:
        try:
            return _format_kst(datetime.fromisoformat(submitted_at))
        except ValueError:
            pass
    return _format_kst(datetime.now(KST))


def _format_kst(moment: datetime) -> str:
    """KST 로 변환해 표기한다. tz 가 없는 값은 UTC 로 간주한다 —
    db.save_review 가 datetime.now().isoformat() 을 저장하고 Cloud Run 컨테이너는 UTC 라,
    변환하지 않으면 최초 push(KST)와 재푸시(UTC)의 '제출 일자'가 9시간 어긋난다."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(KST)
    return f"{moment.year}년 {moment.month}월 {moment.day}일 {moment.strftime('%H:%M:%S')}"


# 백필·스크래핑이 만든 본문은 세 섹션을 이 마커로 묶은 한 덩어리다
# (backfill_statements.parse_readme_sections·clients.get_problem_statement 참조).
_STATEMENT_MARKERS = re.compile(r"【(문제|입력|출력)】\s*")


def split_statement_markers(description: str) -> tuple[str, str, str]:
    """`【문제】…【입력】…【출력】` 한 덩어리를 (문제, 입력, 출력) 으로 되쪼갠다.

    마커가 없으면 전체를 문제 설명으로 본다. 재푸시 경로는 저장된 problem_statement
    하나만 갖고 있어서, 쪼개지 않으면 README 의 `## 입력`·`## 출력` 섹션이 사라진다.
    """
    if not description or "【" not in description:
        return description, "", ""
    parts = _STATEMENT_MARKERS.split(description)
    # parts = [머리말, 라벨1, 본문1, 라벨2, 본문2, ...]
    found = {}
    for i in range(1, len(parts) - 1, 2):
        found[parts[i]] = parts[i + 1].strip()
    if not found:
        return description, "", ""
    return found.get("문제", parts[0].strip()), found.get("입력", ""), found.get("출력", "")


def build_readme(problem_ref: str, title: str,
                 tier_name: str, tags: list, language: str, url: str,
                 description: str = "", input_desc: str = "", output_desc: str = "",
                 review: dict | None = None, submitted_at: str = "") -> str:
    # 호출자가 입력/출력을 따로 주지 않았고 본문에 마커가 있으면 되쪼갠다 — 재푸시가
    # 저장된 본문 하나만 넘겨 세 섹션이 한 덩어리로 뭉치던 문제.
    if description and not (input_desc or output_desc):
        description, input_desc, output_desc = split_statement_markers(description)
    date_str = _submitted_at_str(submitted_at)
    tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "없음"

    lines = [
        f"# [{tier_name}] {title} - {problem_ref}",
        "",
        f"[문제 링크]({url})",
        "",
        "## 성능 요약",
        "",
        "메모리: - KB, 시간: - ms",
        "",
        "## 분류",
        "",
        tags_str,
        "",
        "## 제출 일자",
        "",
        date_str,
    ]
    # CF 본문에는 수식 이미지 마커가 섞여 있다 — 저장소에 그대로 커밋되지 않도록
    # 마크다운 이미지로 바꾼다. 마커가 없는 BOJ 본문에는 아무 영향이 없다.
    if description:
        lines += ["", "## 문제 설명", "", api_client.tex_markers_to_markdown(description)]
    if input_desc:
        lines += ["", "## 입력", "", api_client.tex_markers_to_markdown(input_desc)]
    if output_desc:
        lines += ["", "## 출력", "", api_client.tex_markers_to_markdown(output_desc)]
    if review is not None:
        lines += _review_section_lines(review)
    return "\n".join(lines) + "\n"
