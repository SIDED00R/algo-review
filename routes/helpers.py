from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import db
import clients as api_client


def push_solution(repo: str, token: str, folder: str, file_stem: str,
                  ext: str, code: str, readme: str, msg: str) -> bool:
    """README + 코드 파일을 저장소에 push. 코드 push 성공 여부 반환."""
    api_client.push_file_to_github(repo, token, f"{folder}/README.md", readme, msg)
    return api_client.push_file_to_github(repo, token, f"{folder}/{file_stem}{ext}", code, msg)


def build_solution_target(platform: str, problem_ref, title: str, tier_name: str = "") -> tuple[str, str]:
    """플랫폼별 저장소 폴더명과 커밋 메시지를 조립해 (folder, msg) 반환."""
    if platform == "boj":
        tier_cat = tier_name.split()[0] if tier_name else "Unrated"
        folder = f"백준/{tier_cat}/{problem_ref}번. {title}"
        msg = f"[BOJ] {problem_ref}번. {title}"
    else:
        folder = f"Codeforces/{problem_ref}. {title}"
        msg = f"[Codeforces] {problem_ref}. {title}"
    return folder, msg


def merged_github_target(repo_override: str = "", token_override: str = "") -> tuple[str, str]:
    """override 우선으로 GitHub 저장소/토큰을 병합, 둘 다 없으면 ("", "") 반환."""
    gh_settings = db.get_github_settings()
    github_repo = (repo_override or "").strip() or ((gh_settings.get("target_repo") if gh_settings else "") or "")
    github_token = (token_override or "").strip() or ((gh_settings.get("access_token") if gh_settings else "") or "")
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


def push_review_bundle(repo: str, token: str, *, platform: str, problem_ref: str, title: str,
                       tier_name: str, tags: list, language: str, code: str, url: str = "",
                       review: dict | None = None, description: str = "",
                       input_desc: str = "", output_desc: str = "") -> str:
    """README + 코드 파일을 저장소에 push 하고 폴더 경로를 반환한다. 실패 시 HTTPException(500).

    description 이 비어 있으면 플랫폼별 문제 본문을 자동 수집한다 — LLM 이 아니라 스크래핑이라
    리뷰 없이 올리는 경로에서도 그대로 동작한다.
    """
    ext = api_client._get_file_extension(language)
    url = url or api_client.get_problem_url(platform, problem_ref)
    folder, msg = build_solution_target(platform, problem_ref, title, tier_name)

    if not description:
        sections = (api_client.get_boj_problem_sections(int(problem_ref)) if platform == "boj"
                    else api_client.get_cf_problem_sections(problem_ref))
        description = sections.get("description", "")
        input_desc = sections.get("input", "")
        output_desc = sections.get("output", "")

    readme = build_readme(problem_ref, title, tier_name, tags, language, url,
                          description, input_desc, output_desc, review)
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


def build_readme(problem_ref: str, title: str,
                 tier_name: str, tags: list, language: str, url: str,
                 description: str = "", input_desc: str = "", output_desc: str = "",
                 review: dict | None = None) -> str:
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    date_str = f"{now.year}년 {now.month}월 {now.day}일 {now.strftime('%H:%M:%S')}"
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
