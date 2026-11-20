"""백준 문제 페이지 수집 — 인앱 뷰어(`/api/problem/boj/{번호}`)가 쓰고, 페이지 요청은 리뷰 본문 수집
(`clients.solved_ac`)과 공유한다.

본문은 한국어 원문이라 번역하지 않는다. 섹션 HTML 은 프런트가 DOMPurify 로 정화해 그리고,
수식(`$…$`·`\\(…\\)`)은 KaTeX 가 렌더한다.
"""
import copy
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from clients.utils import BROWSER_USER_AGENT, ProblemNotFound

BOJ_BASE = "https://www.acmicpc.net"

_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 뷰어 섹션 키 → 페이지 요소 id. statement·input·output 은 CF 뷰어의 statement_sections_ko 와 같은 키다.
_SECTION_IDS = {
    "statement": "problem_description",
    "input": "problem_input",
    "output": "problem_output",
    "limit": "problem_limit",
    "hint": "problem_hint",
}


def boj_problem_url(problem_id: int) -> str:
    return f"{BOJ_BASE}/problem/{problem_id}"


def fetch_boj_soup(problem_id: int) -> BeautifulSoup:
    """문제 페이지를 받아 파싱한다. 없는 문제는 ProblemNotFound, 그 밖의 실패는 예외 전파."""
    resp = requests.get(boj_problem_url(problem_id), headers=_HEADERS, timeout=10)
    if resp.status_code == 404:
        raise ProblemNotFound(f"백준에 없는 문제입니다: {problem_id}")
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _absolutize_links(el) -> None:
    """상대 경로 그림·링크를 절대 URL 로 바꾼다 — 앱 도메인에서 그리면 상대 경로가 앱을 가리킨다."""
    for node in el.select("img[src]"):
        node["src"] = urljoin(BOJ_BASE + "/", node["src"])
    for node in el.select("a[href]"):
        node["href"] = urljoin(BOJ_BASE + "/", node["href"])


def _section_html(soup: BeautifulSoup, element_id: str) -> str:
    el = soup.find(id=element_id)
    if el is None:
        return ""
    _absolutize_links(el)
    html = el.decode_contents().strip()
    # 빈 섹션도 요소는 있다(`<div id="problem_hint">\n</div>`) — 글자도 그림도 없으면 비었다고 본다.
    return html if (el.get_text(strip=True) or el.find("img")) else ""


_BLOCK_TAGS = ["p", "div", "li", "tr", "pre", "table", "ul", "ol", "blockquote",
               "h1", "h2", "h3", "h4", "h5", "h6"]


def _script(operator: str, text: str) -> str:
    return f"{operator}{text}" if len(text) <= 1 else f"{operator}{{{text}}}"


def _section_text(soup: BeautifulSoup, element_id: str) -> str:
    """섹션의 텍스트판. 첨자는 `2^{31}`·`F_{n-1}` 로, 줄은 블록 요소 경계에서만 나눈다.

    `get_text("\\n")` 로 평탄화하면 `2<sup>31</sup>` 이 `2` 와 `31` 두 줄이 된다."""
    el = soup.find(id=element_id)
    if el is None:
        return ""
    el = copy.copy(el)   # 화면용 HTML 은 원본 트리에서 뽑는다
    # 안쪽 첨자부터 접는다 — 바깥을 먼저 바꾸면 안쪽 노드가 트리에서 떨어져 replace_with 가 실패한다.
    for node in reversed(el.find_all(["sup", "sub"])):
        node.replace_with(_script("^" if node.name == "sup" else "_", node.get_text(strip=True)))
    for node in el.find_all("br"):
        node.replace_with("\n")
    for node in el.find_all(_BLOCK_TAGS):
        node.append("\n")
    lines = (line.strip() for line in el.get_text().splitlines())
    return "\n".join(line for line in lines if line)


def _limits(soup: BeautifulSoup) -> tuple[str, str]:
    """(시간 제한, 메모리 제한). 열 순서가 아니라 머리글 글자로 찾는다."""
    table = soup.find(id="problem-info")
    if table is None:
        return "", ""
    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    cells = [td.get_text(" ", strip=True) for td in table.select("tbody td")]
    by_header = dict(zip(headers, cells))
    return by_header.get("시간 제한", ""), by_header.get("메모리 제한", "")


def _samples(soup: BeautifulSoup) -> list[dict]:
    """예제 입출력 쌍. 번호로 짝짓는다 — 출력 없는 예제(인터랙티브 등)는 빈 출력으로 둔다.

    앞 공백은 남긴다(격자·그림 입력에서 의미가 있다). 끝 공백·개행만 지운다."""
    samples = []
    number = 1
    while True:
        inp = soup.find(id=f"sample-input-{number}")
        if inp is None:
            return samples
        out = soup.find(id=f"sample-output-{number}")
        samples.append({
            "input": inp.get_text().replace("\r\n", "\n").rstrip(),
            "output": out.get_text().replace("\r\n", "\n").rstrip() if out is not None else "",
        })
        number += 1


def scrape_boj_problem(problem_id: int) -> dict:
    """뷰어 응답의 원재료. 없는 문제는 ProblemNotFound, 요청 실패는 예외 전파.

    sections_text 는 질문 칸 문맥과 GitHub README 본문이 쓰는 텍스트판이다."""
    soup = fetch_boj_soup(problem_id)
    title_el = soup.find(id="problem_title")
    time_limit, memory_limit = _limits(soup)
    sections_text = {key: _section_text(soup, element_id) for key, element_id in _SECTION_IDS.items()}
    sections_html = {key: _section_html(soup, element_id) for key, element_id in _SECTION_IDS.items()}
    if not any(sections_text.values()) and not any(sections_html.values()):
        # 200 인데 본문 요소가 하나도 없다 — 페이지 구조가 바뀌었다. 빈 뷰어를 캐시하지 않게 실패로 올린다.
        raise RuntimeError(f"백준 문제 페이지에서 본문을 찾지 못했습니다: {problem_id}")
    return {
        "problem_id": problem_id,
        "title": title_el.get_text(strip=True) if title_el else f"문제 {problem_id}",
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "sections_html": sections_html,
        "sections_text": sections_text,
        "samples": _samples(soup),
        "url": boj_problem_url(problem_id),
    }
