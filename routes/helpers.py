"""라우터 공용 헬퍼 — GitHub push(README 조립, 저장 폴더·커밋 메시지, 저장소 타깃 병합,
번들 push) · 요청 검증(require_platform · require_language · require_reviewable_code) ·
상류 실패 매핑(upstream_failure · run_llm) · LLM 전제 검사(require_openai_key) ·
평균 난이도 표기(average_difficulty).

push_solution 은 파일별 PUT 이다(가져오기처럼 수백 건을 훑는 경로에서 한 문제가 실패해도
나머지가 진행된다). push_review_bundle 은 README+코드를 한 커밋으로 묶는다(단건 등록은
저장소 이력이 문제 단위로 남는다).
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import db
import clients as api_client
from config import settings
from constants import TIER_NAMES
from routes.models import MAX_CODE_LENGTH, validate_platform

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

    openai SDK 의 `APIStatusError` 메시지에는 제공자 응답 본문과 `base_url` 이 들어간다.
    """
    logger.exception("%s", action)
    return HTTPException(status_code=502, detail=f"{action} ({type(exc).__name__})")


def run_llm(action: str, call, *args, **kwargs):
    """LLM 호출의 예외 매핑. analyzer 가 만든 사용자용 안내(ValueError)는 본문을 그대로
    502 로 보내고, 그 밖의 예외는 upstream_failure 가 타입명만 노출한다.

    HTTPException 을 먼저 통과시킨다 — 삼키면 호출부가 만든 400 이 502 로 바뀐다.
    """
    try:
        return call(*args, **kwargs)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise upstream_failure(action, e)


def require_openai_key(suffix: str = "") -> None:
    """LLM 을 쓰는 라우터의 공통 전제. 설정 누락은 서버 문제라 500 이다."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=500,
                            detail="OPENAI_API_KEY가 설정되지 않았습니다." + suffix)


def average_difficulty(platform: str) -> tuple[float, bool, str]:
    """(평균 난이도, 등급 있는 기록 존재 여부, 표시 라벨).

    두 번째 값이 False 면 평균은 추천용 기본값이라 화면에 그대로 쓰지 않는다.
    """
    if platform == "codeforces":
        avg = db.get_average_cf_rating()
        graded = db.has_cf_rating()
        return avg, graded, f"CF {int(avg)}" if graded else "N/A"
    avg = db.get_average_tier()
    graded = db.has_graded_tier()
    return avg, graded, TIER_NAMES.get(int(avg), "N/A") if graded else "N/A"


def require_platform(value: str) -> str:
    """플랫폼 문자열을 검증해 400 으로 바꾼다.

    validate_platform 은 pydantic 검증용이라 ValueError 를 던진다.
    """
    try:
        return validate_platform(value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def require_reviewable_code(code: str) -> str:
    """LLM 에 넘길 코드의 길이 상한. 저장된 코드를 리뷰하는 경로가 공유한다.

    `ReviewRequest` 는 pydantic 이 요청 본문에서 막지만, 가져오기로 들어온 코드는 그
    검증을 거치지 않는다(`/api/import*` 는 크롤링·API 결과를 그대로 저장한다).
    `analyzer.analyze_code` 는 문제 본문만 자르고 코드는 자르지 않는다.
    """
    if len(code or "") > MAX_CODE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"코드가 {MAX_CODE_LENGTH:,}자를 넘어 리뷰할 수 없습니다. "
                   "리뷰 탭에서 핵심 부분만 붙여 넣어 주세요.")
    return code


def require_language(language: str) -> str:
    """제출 언어를 강제한다. 사용자가 폼에서 언어를 고르는 세 엔드포인트
    (/api/review, /api/review/pending, /api/push-review)가 이 규칙을 공유한다.

    언어를 모르면 확장자가 `.txt` 가 된다. rereview 는 파일명을 재현하지 못해
    재업로드를 거부한다.

    `/api/review-imported` 는 부르지 않는다 — 그 경로의 language 는 가져오기 원본에서
    오므로 요청자가 고칠 수단이 없다.
    """
    value = (language or "").strip()
    if not value:
        raise HTTPException(status_code=400,
                            detail="언어를 선택해주세요. 파일 확장자를 정하는 데 필요합니다.")
    return value


def require_problem_ref(platform: str, problem_ref) -> str:
    """저장소 경로·URL 에 쓸 문제 번호를 플랫폼 형식으로 검증한다.

    통과시키면 `get_problem_url` 이 던지는 ValueError 가 라우터를 그대로 빠져나가
    500 "서버 내부 오류" 가 된다.
    """
    ref = str(problem_ref or "").strip()
    if platform == "boj":
        if not ref.isdigit():
            raise HTTPException(status_code=400, detail="BOJ 문제 번호는 숫자여야 합니다.")
        return ref
    try:
        contest_id, index = api_client.normalize_codeforces_problem_ref(ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return f"{contest_id}{index}"


# 경로 세그먼트 구분자만 바꾼다. `/` 가 제목에 있으면 폴더가 깊어져 재가져오기 파서의
# 4세그먼트 규약에서 빠진다. 나머지 특수문자는 clients.github._url_path 가 인코딩한다.
_PATH_SEPARATORS = str.maketrans({"/": "-", "\\": "-"})


def safe_path_segment(text: str) -> str:
    """문제 제목을 폴더명 한 세그먼트로 쓸 수 있게 만든다."""
    return " ".join(text.translate(_PATH_SEPARATORS).split()).strip(". ") or "제목 없음"


def build_solution_target(platform: str, problem_ref, title: str, tier_name: str = "") -> tuple[str, str]:
    """플랫폼별 저장소 폴더명과 커밋 메시지를 조립해 (folder, msg) 반환."""
    name = safe_path_segment(str(title))
    if platform == "boj":
        # `" "` 는 truthy 지만 split() 이 [] 라 그대로 인덱싱하면 IndexError 다.
        tier_cat = safe_path_segment((tier_name.split() or ["Unrated"])[0])
        folder = f"백준/{tier_cat}/{problem_ref}번. {name}"
        msg = f"[BOJ] {problem_ref}번. {name}"
    else:
        folder = f"Codeforces/{problem_ref}. {name}"
        msg = f"[Codeforces] {problem_ref}. {name}"
    return folder, msg


def merged_github_target(repo_override: str = "", token_override: str = "") -> tuple[str, str]:
    """override 우선으로 GitHub 저장소/토큰을 병합, 둘 다 없으면 ("", "") 반환.

    저장소와 토큰은 **짝으로만** 받는다. 한쪽만 override 하면 나머지가 저장된 값으로
    폴백해, 요청자가 고른 저장소에 저장된 토큰으로 커밋하게 된다 — `scope=repo` 토큰이라
    그 계정이 쓰기 권한을 가진 모든 저장소가 대상이 된다.
    """
    repo = (repo_override or "").strip()
    token = (token_override or "").strip()
    if repo or token:
        if not (repo and token):
            raise HTTPException(
                status_code=400,
                detail="저장소와 토큰은 함께 지정해야 합니다. 한쪽만 주면 저장된 연결 정보와 "
                       "섞여 의도하지 않은 저장소에 커밋될 수 있습니다.")
        return repo, token
    gh_settings = db.get_github_settings()
    if not gh_settings:
        return "", ""
    return gh_settings["target_repo"], gh_settings["access_token"]


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

    description 이 비어 있으면 플랫폼별 문제 본문을 스크래핑한다.

    require_sections: 스크래핑 실패 시 막을지 여부. 기본 True 이되 **저장소에 그 README 가
    실제로 있을 때만** 막는다(지킬 문서가 없으면 최초 등록이 차단된다).
    False 면 확인조차 하지 않는다.

    description 을 직접 주면 input/output 은 호출자 책임이다. `【문제】/【입력】/【출력】`
    마커가 있으면 build_readme 가 세 섹션으로 되쪼갠다.
    """
    ext = api_client.get_file_extension(language)
    # 스크래핑 분기 밖에서 확인한다 — 안에 두면 본문을 함께 보낸 요청이 검증을 건너뛰어
    # `백준/Codeforces/abc번. …` 같은 경로가 저장소에 실제로 커밋된다.
    problem_ref = require_problem_ref(platform, problem_ref)
    url = url or api_client.get_problem_url(platform, problem_ref)
    folder, msg = build_solution_target(platform, problem_ref, title, tier_name)

    # 호출자가 섹션을 하나라도 직접 줬으면 스크래핑하지 않는다. description 만 보고 분기하면
    # description="" + input_desc/output_desc 조합에서 호출자 값이 덮인다.
    if not (description or input_desc or output_desc):
        if platform == "boj":
            sections = api_client.get_boj_problem_sections(int(problem_ref))
        else:
            sections = api_client.get_cf_problem_sections(problem_ref)
        if not sections or not any(sections.values()):
            # 스크래핑 실패를 빈 섹션으로 오인하면 README 를 본문 없이 재생성해 기존 문제 설명을
            # 지운다. None 뿐 아니라 "200 인데 본문이 비었다" 도 실패로 본다.
            # 다만 지킬 문서가 없을 때는 막지 않는다 — 최초 등록이 이유 없이 차단된다.
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
        # push_files_to_github 는 네트워크 오류·401·404·422 를 전부 False 로 삼킨다.
        # 상류 실패로 본다.
        raise HTTPException(status_code=502, detail="GitHub push에 실패했습니다.")
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
    """KST 로 변환해 표기한다. tz 가 없는 값은 UTC 로 간주한다(timestamps.parse_stored 와
    같은 규칙) — 오프셋 없이 저장된 옛 행은 전부 Cloud Run(UTC)이 쓴 것이다."""
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
    # 호출자가 입력/출력을 따로 주지 않았고 본문에 마커가 있으면 되쪼갠다.
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
