from datetime import datetime, timezone, timedelta


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
