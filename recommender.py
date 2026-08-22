from datetime import datetime
from clients import (ProblemSearchError, get_tag_key_by_name,
                     search_cf_problems_by_tag, search_problems_by_tag)
from constants import TIER_NAMES
import db

TIER_RANGE_LOW       = 1
TIER_RANGE_SAME_HIGH = 2
TIER_RANGE_HARD_LOW  = 3
TIER_RANGE_HARD_HIGH = 8
SAME_PER_TAG = 1
HARD_PER_TAG = 2

CF_RANGE_LOW       = 100
CF_RANGE_SAME_HIGH = 100
CF_RANGE_HARD_HIGH = 500


def _score_tags(tag_data: list) -> list:
    if not tag_data:
        return []

    now = datetime.now()
    max_count = max(d["solve_count"] for d in tag_data) or 1

    for d in tag_data:
        try:
            last = datetime.fromisoformat(d["last_solved_at"])
            d["days_since"] = (now - last).days
        except Exception:
            d["days_since"] = 365

    max_days = max(d["days_since"] for d in tag_data) or 1

    for d in tag_data:
        count_score   = 1 - (d["solve_count"] / max_count)
        poor_score    = d["poor_ratio"]
        recency_score = d["days_since"] / max_days
        d["weakness_score"] = (
            count_score   * 0.5 +
            poor_score    * 0.3 +
            recency_score * 0.2
        )

    tag_data.sort(key=lambda x: x["weakness_score"], reverse=True)
    return tag_data


def get_weak_tags_scored(top_n: int = 5, platform: str = "boj") -> list[str]:
    tag_data = db.get_tag_weakness_data(platform=platform)
    scored = _score_tags(tag_data)
    return [d["tag"] for d in scored[:top_n]]


def get_recommendations(weak_tags: list[str], platform: str = "boj",
                        extra_exclude: set | None = None,
                        avg_difficulty: float | None = None) -> list[dict]:
    """취약 태그별 추천 문제.

    weak_tags 와 avg_difficulty 는 호출부가 구해서 넘긴다 — 유일한 호출자
    (routes/recommend.py)가 응답에도 그 값들을 실어야 해서 어차피 먼저 계산한다.
    여기서 다시 조회하면 같은 요청이 reviews 전 행 윈도우 쿼리를 두 번 돈다.
    """
    if not weak_tags:
        return []
    if platform == "codeforces":
        return _get_cf_recommendations(weak_tags, extra_exclude=extra_exclude,
                                       avg_rating=avg_difficulty)

    avg_tier = db.get_average_tier() if avg_difficulty is None else avg_difficulty
    same_min = max(1,  int(avg_tier) - TIER_RANGE_LOW)
    same_max = min(30, int(avg_tier) + TIER_RANGE_SAME_HIGH)
    hard_min = min(30, int(avg_tier) + TIER_RANGE_HARD_LOW)
    hard_max = min(30, int(avg_tier) + TIER_RANGE_HARD_HIGH)

    solved_ids = db.get_solved_problem_ids() | (extra_exclude or set())

    recommendations = []
    failures = 0
    for tag_name in weak_tags:
        tag_key = get_tag_key_by_name(tag_name)

        # 태그마다 별도 HTTP 호출이라 실패를 태그 단위로 격리한다. 하나가 실패해도
        # 나머지 태그의 결과는 살리고, 전부 실패했을 때만 실패로 본다.
        try:
            same_problems = search_problems_by_tag(
                tag_key=tag_key, min_tier=same_min, max_tier=same_max, exclude_ids=solved_ids,
            )[:SAME_PER_TAG]
            hard_problems = search_problems_by_tag(
                tag_key=tag_key, min_tier=hard_min, max_tier=hard_max, exclude_ids=solved_ids,
            )[:HARD_PER_TAG]
        except ProblemSearchError:
            failures += 1
            continue

        problems = same_problems + hard_problems

        if problems:
            for p in problems:
                p["url"] = f"https://boj.kr/{p['id']}"
            recommendations.append({
                "tag": tag_name,
                "tag_key": tag_key,
                "problems": problems,
            })

    if failures == len(weak_tags):
        raise ProblemSearchError("solved.ac 문제 검색에 실패했습니다.")
    return recommendations


def _get_cf_recommendations(weak_tags: list[str], extra_exclude: set | None = None,
                            avg_rating: float | None = None) -> list[dict]:
    if avg_rating is None:
        avg_rating = db.get_average_cf_rating()
    cf_same_min = max(800,  int(avg_rating) - CF_RANGE_LOW)
    cf_same_max = min(3500, int(avg_rating) + CF_RANGE_SAME_HIGH)
    # hard 구간은 same_max 다음 레이팅부터 시작 — 경계값이 양쪽에 걸려 같은 문제가 중복 추천되는 것을 방지
    # (단 avg_rating이 상한 근처면 same_max·hard_min 둘 다 3500으로 클램프되어 경계가 겹칠 수 있음)
    cf_hard_min = min(3500, int(avg_rating) + CF_RANGE_SAME_HIGH + 1)
    cf_hard_max = min(3500, int(avg_rating) + CF_RANGE_HARD_HIGH)

    exclude_refs = db.get_solved_cf_refs() | (extra_exclude or set())

    recommendations = []
    # CF 는 BOJ 와 달리 태그별 실패 격리를 **하지 않는다**. search_cf_problems_by_tag 의
    # 유일한 실패 조건은 프로세스 전역 스냅샷 1개의 실패라 태그와 무관하고, 격리하면
    # 같은 수 MB 다운로드를 태그·밴드 수만큼(최대 6회 × timeout 30s) 직렬 반복한다.
    # BOJ 는 태그마다 별도 HTTP 호출이라 격리가 의미를 갖는다.
    for tag in weak_tags:
        same_problems = search_cf_problems_by_tag(tag, cf_same_min, cf_same_max, exclude_refs)[:SAME_PER_TAG]
        hard_problems = search_cf_problems_by_tag(tag, cf_hard_min, cf_hard_max, exclude_refs)[:HARD_PER_TAG]
        problems = same_problems + hard_problems
        if problems:
            recommendations.append({
                "tag": tag,
                "tag_key": tag,
                "problems": problems,
            })
    return recommendations


def tier_range_description(avg_tier: float) -> str:
    same_min = max(1,  int(avg_tier) - TIER_RANGE_LOW)
    hard_max = min(30, int(avg_tier) + TIER_RANGE_HARD_HIGH)
    return f"{TIER_NAMES.get(same_min, '?')} ~ {TIER_NAMES.get(hard_max, '?')}"


def cf_rating_range_description(avg_rating: float) -> str:
    """BOJ 의 tier_range_description 과 짝. 800/3500 클램프를 한 곳에만 둔다."""
    same_min = max(800,  int(avg_rating) - CF_RANGE_LOW)
    hard_max = min(3500, int(avg_rating) + CF_RANGE_HARD_HIGH)
    return f"CF {same_min} ~ CF {hard_max}"
