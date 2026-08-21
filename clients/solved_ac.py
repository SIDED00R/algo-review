import logging
import time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("uvicorn.error")

SOLVED_AC_BASE = "https://solved.ac/api/v3"

# 정본은 constants.py 다 — DB 레이어가 이 모듈을 import 하던 역의존을 없앴다.
from constants import TIER_NAMES  # noqa: F401  (기존 import 경로 유지)

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
        except Exception as e:
            logger.warning("solved.ac 문제 배치 조회 실패 — 이 묶음은 건너뛴다: %s", e)
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


def get_boj_problem_sections(problem_id: int) -> dict | None:
    """실패 시 None — get_cf_problem_sections 와 같은 계약이다. 호출부(push_review_bundle)가
    빈 섹션으로 착각해 기존 README 본문을 지우지 않도록 구분해야 한다. 예전에는 실패에도
    빈 문자열 dict 를 돌려줘서 `sections is None` 가드가 BOJ 에서 영원히 거짓이었고,
    acmicpc.net 종료 이후 BOJ 재푸시가 이미 올라간 문제 설명을 지우고 있었다.

    200 응답인데 세 섹션이 모두 없는 경우(페이지 구조 변경)도 실패로 본다."""
    try:
        sections = _fetch_boj_sections(problem_id)
    except Exception as e:
        logger.warning("BOJ 문제 섹션 수집 실패 (problem_id=%s): %s", problem_id, e)
        return None
    if not any(sections.values()):
        logger.warning("BOJ 문제 섹션이 비어 있음 — 페이지 구조 변경 가능 (problem_id=%s)", problem_id)
        return None
    return {
        "description": sections["description"] or "",
        "input": sections["input"] or "",
        "output": sections["output"] or "",
    }


def search_problems_by_tag(tag_key: str, min_tier: int, max_tier: int,
                           exclude_ids: set[int]) -> list[dict]:
    tier_code_by_level = _build_tier_key_map()
    # 직접 인덱싱한다 — 맵이 1~30 을 다 채우고 호출처가 모두 그 범위로 클램프하므로
    # 기본값은 도달 불가였다. .get 으로 삼키면 범위를 벗어난 tier 가 조용히 엉뚱한 검색이
    # 되는데(예전 기본값은 "b1"=tier 5, "p5"=tier 16 로 의미와도 어긋났다), 직접
    # 인덱싱하면 KeyError 로 즉시 드러난다.
    min_key = tier_code_by_level[min_tier]
    max_key = tier_code_by_level[max_tier]

    query = f"tag:{tag_key} tier:{min_key}..{max_key} solved:1000.."
    url = f"{SOLVED_AC_BASE}/search/problem"
    params = {
        "query": query,
        "page": 1,
        "sort": "solved",
        "direction": "desc",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
    except Exception as e:
        # 전면 실패를 빈 목록으로 돌려주면 호출부가 "조건에 맞는 문제 없음"과 구분할 수 없다.
        logger.warning("solved.ac 태그 검색 실패 — 추천/테마가 빈 결과가 된다: %s", e)
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
                # .get 으로 받는다 — KeyError 가 나면 except 가 삼켜 캐시가 절반만
                # 채워진 상태로 남는다(_extract_tag_names 와 같은 방어 수준).
                name = d.get("name")
                if name:
                    _TAG_KEY_CACHE[name.lower()] = key
            _TAG_KEY_CACHE[key.lower()] = key
        result = _TAG_KEY_CACHE.get(tag_name.lower())
        if result:
            return result
    except Exception as e:
        logger.warning("solved.ac 태그 목록 조회 실패 (%s): %s", tag_name, e)
    # 폴백도 캐시한다 — 캐시하지 않으면 목록에 없는 태그가 호출마다 전체 태그 목록을
    # 다시 내려받는다(취약 태그 순회에서 최악 3회 풀 페치).
    fallback = tag_name.lower().replace(" ", "_")
    _TAG_KEY_CACHE[tag_name.lower()] = fallback
    return fallback


class BojCrawlError(Exception):
    """acmicpc 요청 자체가 실패했음(네트워크 오류·차단 등) — 정상 응답인데 결과가 없는 것과 구분한다."""


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
        except Exception as e:
            # 첫 페이지 요청 자체가 실패 — 네트워크 오류·차단 등. "결과 없음"과 구분해 알린다.
            if top is None:
                raise BojCrawlError(f"BOJ 제출 목록 조회 실패: {e}") from e
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tbody = soup.select_one("table.table-striped tbody")
        if not tbody:
            # 정상 응답이면 제출이 0건이어도 테이블 뼈대는 존재한다 — 아예 없다면 페이지 형식이
            # 예상과 다르다(로그인 리다이렉트·차단 등). 첫 페이지에서만 실패로 본다.
            if top is None:
                raise BojCrawlError("BOJ 제출 목록 페이지 형식이 예상과 다릅니다.")
            break

        rows = tbody.select("tr[id^='solution-']")
        if not rows:
            break  # 결과 없음(정상) — 더 이상 페이지가 없거나 애초에 제출 기록이 없다.

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
    except Exception as e:
        logger.warning("BOJ 제출 코드 조회 실패 (submission_id=%s): %s", submission_id, e)
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
