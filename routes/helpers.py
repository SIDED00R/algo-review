from datetime import datetime, timezone, timedelta
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


def build_readme(problem_ref: str, title: str,
                 tier_name: str, tags: list, language: str, url: str,
                 description: str = "", input_desc: str = "", output_desc: str = "") -> str:
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
    if description:
        lines += ["", "## 문제 설명", "", description]
    if input_desc:
        lines += ["", "## 입력", "", input_desc]
    if output_desc:
        lines += ["", "## 출력", "", output_desc]
    return "\n".join(lines) + "\n"
