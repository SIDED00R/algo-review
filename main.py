"""
Algo Review CLI
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.markdown import Markdown

load_dotenv()

import db
import clients as api_client
import analyzer
import recommender

console = Console()


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def check_api_key():
    if not os.environ.get("OPENAI_API_KEY"):
        console.print("[bold red]오류:[/] OPENAI_API_KEY가 설정되지 않았습니다.")
        console.print("  .env 파일에 OPENAI_API_KEY=sk-proj-... 를 추가하세요.")
        sys.exit(1)


def tier_color(tier: int) -> str:
    if tier == 0:
        return "white"
    elif tier <= 5:
        return "dark_orange"
    elif tier <= 10:
        return "grey70"
    elif tier <= 15:
        return "yellow"
    elif tier <= 20:
        return "cyan"
    elif tier <= 25:
        return "blue"
    else:
        return "red"


def efficiency_badge(e: str) -> str:
    badges = {"good": "[green]● 효율적[/]", "ok": "[yellow]◐ 보통[/]", "poor": "[red]● 비효율적[/]"}
    return badges.get(e, e)


def read_code_from_input() -> str:
    console.print("\n[bold cyan]풀이 코드를 붙여넣고, 완료되면 빈 줄에 [END] 를 입력하세요:[/]")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "[END]":
            break
        lines.append(line)
    return "\n".join(lines)


def read_code_from_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {path}[/]")
        sys.exit(1)
    return p.read_text(encoding="utf-8")


# ──────────────────────────────────────────────
# 메뉴 액션
# ──────────────────────────────────────────────

def action_review():
    check_api_key()

    # 문제 번호 입력
    while True:
        pid_str = Prompt.ask("[bold]백준 문제 번호[/]")
        if pid_str.isdigit():
            problem_id = int(pid_str)
            break
        console.print("[red]숫자를 입력하세요.[/]")

    # 코드 입력 방식 선택
    mode = Prompt.ask("코드 입력 방식", choices=["직접입력", "파일경로"], default="직접입력")
    if mode == "파일경로":
        fpath = Prompt.ask("파일 경로")
        code = read_code_from_file(fpath)
    else:
        code = read_code_from_input()

    if not code.strip():
        console.print("[red]코드가 비어있습니다.[/]")
        return

    # 문제 정보 가져오기
    with console.status("[cyan]문제 정보 가져오는 중...[/]"):
        try:
            problem_info = api_client.get_problem_info(problem_id)
        except Exception as e:
            console.print(f"[red]문제 정보 조회 실패: {e}[/]")
            return

    tier_c = tier_color(problem_info["tier"])
    console.print(Panel(
        f"[bold]{problem_info['title']}[/]  "
        f"[{tier_c}]{problem_info['tier_name']}[/]\n"
        f"태그: {', '.join(problem_info['tags']) or '없음'}",
        title=f"[bold]BOJ {problem_id}[/]",
        border_style="cyan",
    ))

    # 문제 설명 크롤링
    with console.status("[cyan]문제 설명 크롤링 중...[/]"):
        statement = api_client.get_problem_statement(problem_id)

    with console.status("[cyan]AI가 코드를 분석 중입니다...[/]"):
        try:
            result = analyzer.analyze_code(problem_info, statement, code)
        except Exception as e:
            console.print(f"[red]코드 분석 실패: {e}[/]")
            return

    # 분석 결과 출력
    console.print()
    console.print(Panel(
        f"효율성: {efficiency_badge(result['efficiency'])}\n"
        f"시간복잡도: [bold]{result.get('complexity', 'N/A')}[/]\n"
        + (f"더 나은 알고리즘: [yellow]{result['better_algorithm']}[/]\n"
           if result.get('better_algorithm') else ""),
        title="[bold]분석 요약[/]",
        border_style="green",
    ))

    if result.get("strengths"):
        console.print("[bold green]✓ 잘한 점[/]")
        for s in result["strengths"]:
            console.print(f"  • {s}")

    if result.get("weaknesses"):
        console.print("\n[bold yellow]✗ 개선할 점[/]")
        for w in result["weaknesses"]:
            console.print(f"  • {w}")

    console.print("\n[bold]상세 피드백[/]")
    console.print(Markdown(result.get("feedback", "")))

    # DB 저장
    db.save_review(
        problem_id=problem_id,
        title=problem_info["title"],
        tier=problem_info["tier"],
        tags=problem_info["tags"],
        code=code,
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
    )
    console.print("\n[dim]리뷰가 저장되었습니다.[/]")


def action_recommend():
    avg_tier = db.get_average_tier()
    weak_tags = db.get_weak_tags(5)

    if not weak_tags:
        console.print("[yellow]아직 분석 데이터가 없습니다. 먼저 코드 리뷰를 진행하세요.[/]")
        return

    tier_desc = recommender.tier_range_description(avg_tier)
    console.print(Panel(
        f"평균 티어: [bold]{api_client.TIER_NAMES.get(int(avg_tier), 'N/A')}[/] ({avg_tier:.1f})\n"
        f"추천 난이도 범위: [bold]{tier_desc}[/]\n"
        f"취약 태그: {', '.join(weak_tags[:5])}",
        title="[bold]추천 기준[/]",
        border_style="yellow",
    ))

    with console.status("[cyan]문제 검색 중...[/]"):
        recs = recommender.get_recommendations(top_weak_tags=3)

    if not recs:
        console.print("[yellow]추천할 문제를 찾지 못했습니다. 다른 난이도 범위를 시도해보세요.[/]")
        return

    for rec in recs:
        table = Table(
            title=f"[bold cyan]{rec['tag']}[/] 태그 추천 문제",
            box=box.ROUNDED,
            border_style="cyan",
        )
        table.add_column("번호", style="dim", width=8)
        table.add_column("제목", min_width=25)
        table.add_column("난이도", width=14)
        table.add_column("링크", style="blue underline")

        for p in rec["problems"]:
            tc = tier_color(p["tier"])
            table.add_row(
                str(p["id"]),
                p["title"],
                f"[{tc}]{p['tier_name']}[/]",
                f"https://boj.kr/{p['id']}",
            )

        console.print(table)
        console.print()


def action_stats():
    tag_stats = db.get_tag_stats()
    history = db.get_review_history(10)

    if not tag_stats:
        console.print("[yellow]아직 저장된 기록이 없습니다.[/]")
        return

    # 태그 통계 테이블
    table = Table(title="태그별 풀이 통계", box=box.ROUNDED)
    table.add_column("태그", min_width=20)
    table.add_column("총횟수", justify="right", width=8)
    table.add_column("잘함", justify="right", width=8, style="green")
    table.add_column("부족", justify="right", width=8, style="red")
    table.add_column("취약도", justify="right", width=10)

    for s in tag_stats:
        ratio = s["poor_count"] / s["total_count"] if s["total_count"] > 0 else 0
        bar = "█" * int(ratio * 10) + "░" * (10 - int(ratio * 10))
        table.add_row(
            s["tag"],
            str(s["total_count"]),
            str(s["good_count"]),
            str(s["poor_count"]),
            f"[red]{bar}[/]" if ratio > 0.5 else f"[yellow]{bar}[/]",
        )

    console.print(table)

    # 최근 기록
    if history:
        console.print()
        htable = Table(title="최근 풀이 기록", box=box.SIMPLE)
        htable.add_column("문제", min_width=25)
        htable.add_column("티어", width=14)
        htable.add_column("평가", width=12)
        htable.add_column("날짜", width=12)

        for r in history:
            tc = tier_color(r["tier"])
            htable.add_row(
                f"[link=https://boj.kr/{r['problem_id']}]{r['title']}[/link]",
                f"[{tc}]{api_client.TIER_NAMES.get(r['tier'], '?')}[/]",
                efficiency_badge(r["efficiency"]),
                r["created_at"][:10],
            )

        console.print(htable)


def action_report():
    check_api_key()
    tag_stats = db.get_tag_stats()
    history = db.get_review_history(10)

    if not tag_stats:
        console.print("[yellow]아직 저장된 기록이 없습니다.[/]")
        return

    with console.status("[cyan]종합 분석 리포트 생성 중...[/]"):
        report = analyzer.get_cumulative_analysis(tag_stats, history)

    console.print(Panel(Markdown(report), title="[bold]종합 분석 리포트[/]", border_style="magenta"))


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────

MENU = {
    "1": ("코드 리뷰", action_review),
    "2": ("문제 추천", action_recommend),
    "3": ("통계 보기", action_stats),
    "4": ("종합 분석 리포트", action_report),
    "0": ("종료", None),
}


def print_menu():
    console.print(Panel(
        "\n".join(f"  [bold cyan]{k}[/]  {v[0]}" for k, v in MENU.items()),
        title="[bold magenta]Algo Review[/]",
        border_style="magenta",
    ))


def main():
    db.init_db()

    console.print("[bold magenta]Algo Review 시스템[/]")
    console.print("[dim]OpenAI API + solved.ac 기반[/]\n")

    while True:
        print_menu()
        choice = Prompt.ask("메뉴 선택", choices=list(MENU.keys()), default="1")

        if choice == "0":
            console.print("[dim]종료합니다.[/]")
            break

        console.print()
        try:
            MENU[choice][1]()
        except KeyboardInterrupt:
            console.print("\n[dim]취소되었습니다.[/]")
        except Exception as e:
            console.print(f"[red]오류 발생: {e}[/]")

        console.print()
        if not Confirm.ask("계속하시겠습니까?", default=True):
            break


if __name__ == "__main__":
    main()
