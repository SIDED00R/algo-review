import logging
import time
import requests
from bs4 import BeautifulSoup

# TIER_NAMES 의 정본은 constants.py 다 — 여기 두면 DB 레이어가 이 모듈을 import 하게 된다.
from clients.utils import ProblemSearchError
from constants import TIER_NAMES

logger = logging.getLogger("uvicorn.error")

SOLVED_AC_BASE = "https://solved.ac/api/v3"

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
    """BOJ 문제 페이지의 세 섹션을 담은 dict. 페이지에 없는 섹션은 값이 None 이다. 요청 실패는 예외 전파."""
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
    """실패 시 None — get_cf_problem_sections 와 같은 계약이다.

    호출부(push_review_bundle)가 "수집 실패" 와 "본문이 비어 있음" 을 구분해야 한다.
    구분하지 못하면 본문 없는 README 로 덮어써 이미 올라간 문제 설명을 지운다.
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
    # 직접 인덱싱한다 — 맵이 1~30 을 다 채우고 호출처가 그 범위로 클램프한다.
    # .get 으로 삼키면 범위 밖 tier 가 조용히 엉뚱한 검색이 된다.
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
        logger.warning("solved.ac 태그 검색 실패: %s", e)
        raise ProblemSearchError("solved.ac 문제 검색에 실패했습니다.") from e

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


# 성공 조회로 얻은 키만 담는다(만료 없는 캐시다). 추측 키로 검색하면 200 + 빈 목록이라
# ProblemSearchError 도 나지 않고 추천이 조용히 빈다.
_TAG_KEY_CACHE: dict[str, str] = {}

# 추측 키는 만료를 달아 따로 둔다. 두 가지 실패를 구분한다:
#   - 조회 자체가 실패(장애·차단): 짧게
#   - 조회는 성공했는데 목록에 없음: 안정적인 사실이므로 길게
_FALLBACK_TTL_UNREACHABLE = 60
_FALLBACK_TTL_ABSENT = 3600
_TAG_KEY_FALLBACK: dict[str, tuple[str, float]] = {}   # key_lower -> (추측 키, 만료 시각)


def _remember_guess(key_lower: str, ttl: float) -> str:
    """이름을 그대로 키로 쓰는 추측값을 만료와 함께 기록하고 돌려준다."""
    guess = key_lower.replace(" ", "_")
    _TAG_KEY_FALLBACK[key_lower] = (guess, time.time() + ttl)
    return guess


def get_tag_key_by_name(tag_name: str) -> str:
    key_lower = tag_name.lower()
    cached = _TAG_KEY_CACHE.get(key_lower)
    if cached is not None:
        return cached
    guess = _TAG_KEY_FALLBACK.get(key_lower)
    if guess is not None and time.time() < guess[1]:
        return guess[0]

    url = f"{SOLVED_AC_BASE}/tag/list"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            # `or ""` 로 받는다 — JSON 의 `"key": null` 은 .get 이 None 을 주고 .lower() 가
            # AttributeError 를 낸다.
            key = item.get("key") or ""
            if not key:
                continue
            for d in item.get("displayNames", []):
                name = d.get("name")
                if name:
                    _TAG_KEY_CACHE[name.lower()] = key
            _TAG_KEY_CACHE[key.lower()] = key
        result = _TAG_KEY_CACHE.get(key_lower)
        if result:
            return result
        return _remember_guess(key_lower, _FALLBACK_TTL_ABSENT)
    except Exception as e:
        logger.warning("solved.ac 태그 목록 조회 실패 (%s): %s", tag_name, e)
    return _remember_guess(key_lower, _FALLBACK_TTL_UNREACHABLE)


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
