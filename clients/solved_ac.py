import time
import requests
from bs4 import BeautifulSoup

SOLVED_AC_BASE = "https://solved.ac/api/v3"

TIER_NAMES = {
    0: "Unrated",
    1: "Bronze V", 2: "Bronze IV", 3: "Bronze III", 4: "Bronze II", 5: "Bronze I",
    6: "Silver V", 7: "Silver IV", 8: "Silver III", 9: "Silver II", 10: "Silver I",
    11: "Gold V", 12: "Gold IV", 13: "Gold III", 14: "Gold II", 15: "Gold I",
    16: "Platinum V", 17: "Platinum IV", 18: "Platinum III", 19: "Platinum II", 20: "Platinum I",
    21: "Diamond V", 22: "Diamond IV", 23: "Diamond III", 24: "Diamond II", 25: "Diamond I",
    26: "Ruby V", 27: "Ruby IV", 28: "Ruby III", 29: "Ruby II", 30: "Ruby I",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://solved.ac/",
    "Origin": "https://solved.ac",
}


def _extract_tag_names(data: dict) -> list[str]:
    tags = []
    for tag in data.get("tags", []):
        display_names = tag.get("displayNames", [])
        # 스키마가 흔들려도 KeyError 로 import 전체를 죽이지 않는다(호출부 루프가 try 밖이다).
        ko = next((d.get("name") for d in display_names if d.get("language") == "ko"), None)
        en = next((d.get("name") for d in display_names if d.get("language") == "en"), None)
        name = ko or en or tag.get("key", "")
        if name:
            tags.append(name)
    return tags


def get_problems_bulk(problem_ids: list[int]) -> dict[int, dict]:
    result = {}
    for i in range(0, len(problem_ids), 100):
        batch = problem_ids[i:i + 100]
        url = f"{SOLVED_AC_BASE}/problem/lookup"
        try:
            resp = requests.get(
                url,
                params={"problemIds": ",".join(str(p) for p in batch)},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception:
            continue

        for data in items:
            pid = data.get("problemId")
            if not pid:
                continue
            tags = _extract_tag_names(data)
            tier = data.get("level", 0)
            result[pid] = {
                "id": pid,
                "title": data.get("titleKo") or data.get("title", f"문제 {pid}"),
                "tier": tier,
                "tier_name": TIER_NAMES.get(tier, "Unknown"),
                "tags": tags,
            }
    return result


def get_problem_info(problem_id: int) -> dict:
    url = f"{SOLVED_AC_BASE}/problem/show"
    resp = requests.get(url, params={"problemId": problem_id}, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    tags = _extract_tag_names(data)
    tier = data.get("level", 0)
    return {
        "id": problem_id,
        "title": data.get("titleKo") or data.get("title", f"문제 {problem_id}"),
        "tier": tier,
        "tier_name": TIER_NAMES.get(tier, "Unknown"),
        "tags": tags,
    }


def _fetch_boj_sections(problem_id: int) -> dict:
    """BOJ 문제 페이지에서 설명/입력/출력 섹션을 가져온다. 요소가 없으면 None, 실패 시 예외 전파."""
    url = f"https://www.acmicpc.net/problem/{problem_id}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def _text(sel):
        el = soup.select_one(sel)
        return el.get_text(separator="\n", strip=True) if el else None

    return {
        "description": _text("#problem_description"),
        "input": _text("#problem_input"),
        "output": _text("#problem_output"),
    }


def get_problem_statement(problem_id: int) -> str:
    try:
        sections = _fetch_boj_sections(problem_id)

        parts = []
        if sections["description"] is not None:
            parts.append("【문제】\n" + sections["description"])
        if sections["input"] is not None:
            parts.append("【입력】\n" + sections["input"])
        if sections["output"] is not None:
            parts.append("【출력】\n" + sections["output"])

        return "\n\n".join(parts) if parts else "문제 설명을 가져올 수 없습니다."
    except Exception as e:
        return f"크롤링 실패: {e}"


def get_boj_problem_sections(problem_id: int) -> dict:
    try:
        sections = _fetch_boj_sections(problem_id)
        return {
            "description": sections["description"] or "",
            "input": sections["input"] or "",
            "output": sections["output"] or "",
        }
    except Exception:
        return {"description": "", "input": "", "output": ""}


def search_problems_by_tag(tag_key: str, min_tier: int, max_tier: int,
                           exclude_ids: set[int], page: int = 1) -> list[dict]:
    tier_map_inv = _build_tier_key_map()
    min_key = tier_map_inv.get(min_tier, "b1")
    max_key = tier_map_inv.get(max_tier, "p5")

    query = f"tag:{tag_key} tier:{min_key}..{max_key} solved:1000.."
    url = f"{SOLVED_AC_BASE}/search/problem"
    params = {
        "query": query,
        "page": page,
        "sort": "solved",
        "direction": "desc",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
    except Exception:
        return []

    results = []
    for item in items:
        pid = item.get("problemId")
        if pid in exclude_ids:
            continue
        tier = item.get("level", 0)
        results.append({
            "id": pid,
            "title": item.get("titleKo") or item.get("title", f"문제 {pid}"),
            "tier": tier,
            "tier_name": TIER_NAMES.get(tier, "Unknown"),
        })

    return results


_TAG_KEY_CACHE: dict[str, str] = {}


def get_tag_key_by_name(tag_name: str) -> str:
    cached = _TAG_KEY_CACHE.get(tag_name.lower())
    if cached is not None:
        return cached

    url = f"{SOLVED_AC_BASE}/tag/list"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            key = item.get("key", "")
            display_names = item.get("displayNames", [])
            for d in display_names:
                _TAG_KEY_CACHE[d["name"].lower()] = key
            _TAG_KEY_CACHE[key.lower()] = key
        result = _TAG_KEY_CACHE.get(tag_name.lower())
        if result:
            return result
    except Exception:
        pass
    return tag_name.lower().replace(" ", "_")


def get_user_submissions(boj_id: str, max_pages: int = 5) -> list[dict]:
    submissions = []
    seen_ids = set()
    top = None

    for _ in range(max_pages):
        params = {
            "from_mine": "1",
            "user_id": boj_id,
            "result_id": "4",
        }
        if top is not None:
            params["top"] = top

        try:
            resp = requests.get(
                "https://www.acmicpc.net/status",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tbody = soup.select_one("table.table-striped tbody")
        if not tbody:
            break

        rows = tbody.select("tr[id^='solution-']")
        if not rows:
            break

        min_id = None
        for row in rows:
            row_id = row.get("id", "")
            try:
                submission_id = int(row_id.replace("solution-", ""))
            except ValueError:
                continue

            prob_link = row.select_one("a[href^='/problem/']")
            if not prob_link:
                continue
            try:
                problem_id = int(prob_link.get_text(strip=True))
            except ValueError:
                continue

            tds = row.select("td")
            language = tds[6].get_text(strip=True) if len(tds) > 6 else ""

            if problem_id not in seen_ids:
                submissions.append({
                    "submission_id": submission_id,
                    "problem_id": problem_id,
                    "language": language,
                })
                seen_ids.add(problem_id)

            if min_id is None or submission_id < min_id:
                min_id = submission_id

        if min_id is None:
            break
        top = min_id - 1
        time.sleep(0.5)

    return submissions


def get_submission_code(submission_id: int, session_cookie: str) -> str | None:
    url = f"https://www.acmicpc.net/source/{submission_id}"
    cookies = {"OnlineJudge": session_cookie, "bojsession": session_cookie}
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in [
            "textarea#code",
            "textarea[name='source']",
            "#source-code pre",
            ".highlight pre",
            "pre.prettyprint",
        ]:
            el = soup.select_one(sel)
            if el:
                return el.get_text()
    except Exception:
        pass
    return None


def _build_tier_key_map() -> dict[int, str]:
    codes = [
        "b5","b4","b3","b2","b1",
        "s5","s4","s3","s2","s1",
        "g5","g4","g3","g2","g1",
        "p5","p4","p3","p2","p1",
        "d5","d4","d3","d2","d1",
        "r5","r4","r3","r2","r1",
    ]
    return {i + 1: codes[i] for i in range(len(codes))}
