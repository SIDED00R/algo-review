import re
import time
import random
import hashlib
from functools import lru_cache
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup

CODEFORCES_API_BASE = "https://codeforces.com/api"

CODEFORCES_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def normalize_codeforces_problem_ref(problem_ref: str) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)\s*[-/_ ]?\s*([A-Za-z][A-Za-z0-9]*)\s*$", problem_ref or "")
    if not match:
        raise ValueError("Codeforces 문제는 '4A' 또는 '4/A' 형식으로 입력해주세요.")
    contest_id = int(match.group(1))
    index = match.group(2).upper()
    return contest_id, index


def get_codeforces_problem_info(problem_ref: str) -> dict:
    from clients.utils import get_problem_url
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    problem = _get_codeforces_problem_lookup().get((contest_id, index))
    if not problem:
        raise ValueError(f"Codeforces 문제를 찾을 수 없습니다: {contest_id}{index}")

    rating = problem.get("rating")
    rating_label = f"Codeforces {rating}" if rating else "Codeforces Unrated"
    return {
        "id": 0,
        "platform": "codeforces",
        "problem_ref": f"{contest_id}{index}",
        "contest_id": contest_id,
        "index": index,
        "title": problem.get("name", f"Problem {contest_id}{index}"),
        "tier": 0,
        "tier_name": rating_label,
        "tags": problem.get("tags", []),
        "url": get_problem_url("codeforces", f"{contest_id}{index}"),
    }


def get_codeforces_problem_statement(problem_ref: str) -> str:
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    urls = [
        f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
        f"https://codeforces.com/contest/{contest_id}/problem/{index}",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            statement = soup.select_one(".problem-statement")
            if statement:
                return statement.get_text(separator="\n", strip=True)
        except Exception:
            continue

    return "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 제한적으로 분석합니다."


def cf_xpath_text(tree, expr: str) -> str:
    nodes = tree.xpath(expr)
    if not nodes:
        return ""
    el = nodes[0]
    # script/noscript/style 텍스트는 MathJax 마크업이라 itertext()에 포함되면 수식 중복 발생
    for unwanted in el.xpath(
        './/*[self::script or self::noscript or self::style'
        ' or contains(@class,"section-title")]'
    ):
        p = unwanted.getparent()
        if p is not None:
            p.remove(unwanted)
    return " ".join(el.itertext()).strip()


def get_cf_problem_sections(problem_ref: str) -> dict:
    try:
        from lxml import etree

        contest_id, index = normalize_codeforces_problem_ref(problem_ref)
        url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
        resp.raise_for_status()

        tree = etree.fromstring(resp.text.encode(), etree.HTMLParser())
        BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'
        return {
            "description": cf_xpath_text(tree, f'{BASE}/div[2]'),
            "input":       cf_xpath_text(tree, f'{BASE}/div[3]'),
            "output":      cf_xpath_text(tree, f'{BASE}/div[4]'),
        }
    except Exception:
        return {"description": "", "input": "", "output": ""}


def scrape_cf_problem(problem_ref: str) -> dict:
    """CF 문제 페이지에서 제목/제한/본문/예제/노트를 raw(미번역)로 추출. 형식 오류 시 ValueError."""
    from lxml import etree

    m = re.match(r'^(\d+)([A-Za-z]\d*)$', problem_ref.strip())
    if not m:
        raise ValueError("잘못된 문제 번호 형식 (예: 4A, 1234B)")
    contest_id, index = m.group(1), m.group(2).upper()

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    resp = requests.get(url, timeout=10, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    resp.raise_for_status()

    tree = etree.fromstring(resp.text.encode(), etree.HTMLParser())

    def _limit_value(xpath_expr: str) -> str:
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return ""
        el = nodes[0]
        prop_nodes = el.xpath('.//*[contains(@class,"property-title")]')
        prop_text = " ".join(prop_nodes[0].itertext()).strip() if prop_nodes else ""
        full_text = " ".join(el.itertext()).strip()
        return full_text.replace(prop_text, "", 1).strip()

    BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'

    note_nodes = tree.xpath('//*[contains(@class,"note")]')
    note_text = " ".join(note_nodes[0].itertext()).strip() if note_nodes else ""

    samples = []
    sample_container = tree.xpath(f'{BASE}/div[5]')
    if sample_container:
        sc = sample_container[0]
        inp_pres = sc.xpath('.//div[contains(@class,"input")]//pre')
        out_pres = sc.xpath('.//div[contains(@class,"output")]//pre')
        for inp_pre, out_pre in zip(inp_pres, out_pres):
            samples.append({
                "input":  "\n".join(inp_pre.itertext()).strip(),
                "output": "\n".join(out_pre.itertext()).strip(),
            })

    return {
        "title": cf_xpath_text(tree, '//div[@class="title"]') or f"CF {problem_ref}",
        "time_limit": _limit_value('//div[contains(@class,"time-limit")]'),
        "memory_limit": _limit_value('//div[contains(@class,"memory-limit")]'),
        "statement": cf_xpath_text(tree, f'{BASE}/div[2]'),
        "input": cf_xpath_text(tree, f'{BASE}/div[3]'),
        "output": cf_xpath_text(tree, f'{BASE}/div[4]'),
        "note": note_text,
        "samples": samples,
        "url": url,
        "contest_id": contest_id,
        "index": index,
    }


def _codeforces_api_request(method_name: str, params: dict | None = None,
                            api_key: str | None = None, api_secret: str | None = None) -> dict:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    params["lang"] = "en"

    if api_key and api_secret:
        now = int(time.time())
        rand = f"{random.randint(0, 999999):06d}"
        signed_params = {**params, "apiKey": api_key, "time": now}
        sorted_items = sorted((str(k), str(v)) for k, v in signed_params.items())
        query = urlencode(sorted_items)
        sig_base = f"{rand}/{method_name}?{query}#{api_secret}"
        api_sig = rand + hashlib.sha512(sig_base.encode("utf-8")).hexdigest()
        signed_params["apiSig"] = api_sig
        params = signed_params

    resp = requests.get(
        f"{CODEFORCES_API_BASE}/{method_name}",
        params=params,
        headers=CODEFORCES_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "OK":
        raise ValueError(payload.get("comment", "Codeforces API 오류"))
    return payload["result"]


@lru_cache(maxsize=1)
def _get_codeforces_problem_lookup() -> dict[tuple[int, str], dict]:
    lookup = {}
    result = _codeforces_api_request("problemset.problems")
    for problem in result.get("problems", []):
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if contest_id and index:
            lookup[(contest_id, index)] = problem
    return lookup


def get_codeforces_user_info(handle: str) -> dict:
    users = _codeforces_api_request("user.info", {"handles": handle})
    if not users:
        raise ValueError("Codeforces 유저를 찾을 수 없습니다.")
    return users[0]


def get_codeforces_user_submissions(handle: str, count: int = 1000,
                                    api_key: str | None = None,
                                    api_secret: str | None = None) -> list[dict]:
    from clients.utils import get_problem_url
    result = _codeforces_api_request(
        "user.status",
        {"handle": handle, "from": 1, "count": count, "includeSources": "true" if api_key and api_secret else None},
        api_key=api_key,
        api_secret=api_secret,
    )
    submissions = []
    seen = set()
    for sub in result:
        if sub.get("verdict") != "OK":
            continue
        problem = sub.get("problem") or {}
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if not contest_id or not index:
            continue
        problem_ref = f"{contest_id}{index}"
        if problem_ref in seen:
            continue
        seen.add(problem_ref)
        submissions.append({
            "problem_id": 0,
            "problem_ref": problem_ref,
            "contest_id": contest_id,
            "index": index,
            "title": problem.get("name", problem_ref),
            "tier": 0,
            "tier_name": f"Codeforces {problem['rating']}" if problem.get("rating") else "Codeforces Unrated",
            "tags": problem.get("tags", []),
            "language": sub.get("programmingLanguage", ""),
            "code": sub.get("source", "") or "",
            "submission_id": sub.get("id"),
            "problem_url": get_problem_url("codeforces", problem_ref),
        })
    return submissions


def search_cf_problems_by_tag(tag: str, min_rating: int, max_rating: int,
                               exclude_refs: set) -> list[dict]:
    try:
        resp = requests.get(f"{CODEFORCES_API_BASE}/problemset.problems", params={"tags": tag}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            return []
        problems = data["result"]["problems"]
        stats_map = {
            (s["contestId"], s["index"]): s["solvedCount"]
            for s in data["result"].get("problemStatistics", [])
        }
    except Exception:
        return []

    results = []
    for p in problems:
        rating = p.get("rating", 0)
        if not rating or not (min_rating <= rating <= max_rating):
            continue
        contest_id = p.get("contestId")
        index = p.get("index", "")
        if not contest_id:
            continue
        ref = f"{contest_id}{index}"
        if ref in exclude_refs:
            continue
        results.append({
            "id": ref,
            "title": p.get("name", ref),
            "tier": 0,
            "tier_name": f"CF {rating}",
            "url": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
            "_solved_count": stats_map.get((contest_id, index), 0),
        })

    results.sort(key=lambda x: -x["_solved_count"])
    for r in results:
        del r["_solved_count"]
    return results
