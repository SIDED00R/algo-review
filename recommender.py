from datetime import datetime, timezone
from clients import (ProblemSearchError, get_tag_key_by_name,
                     search_cf_problems_by_tag, search_problems_by_tag)
from constants import TIER_NAMES
from timestamps import parse_stored
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

    now = datetime.now(timezone.utc)
    max_count = max(d["solve_count"] for d in tag_data) or 1

    for d in tag_data:
        # parse_stored 로 aware 로 맞춘다. naive 로 두면 TypeError 가 난다.
        try:
            # 미래 시각(시계 되돌림·수동 편집)은 0 으로 깎는다. 음수 recency 점수는
            # 그 태그를 순위 밑으로 민다.
            d["days_since"] = max(0, (now - parse_stored(d["last_solved_at"])).days)
        except (TypeError, ValueError):
            # 값이 없거나(첫 집계 전) 형식이 깨진 경우만 — '아주 오래 전' 으로 둔다.
            d["days_since"] = 365

    # 0 으로 나누지 않는다. 전부 오늘이면 최신성으로는 우열이 없다는 뜻이라 값은 0 이 된다.
    max_days = max(1, max(d["days_since"] for d in tag_data))

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

        # 태그마다 별도 HTTP 호출이라 실패를 밴드 단위로도 격리한다. 실패한 밴드는 빈
        # 결과로 두고, 두 밴드 모두 실패한 태그만 실패로 본다.
        try:
            same_problems = search_problems_by_tag(
                tag_key=tag_key, min_tier=same_min, max_tier=same_max, exclude_ids=solved_ids,
            )[:SAME_PER_TAG]
        except ProblemSearchError:
            same_problems = []
            same_failed = True
        else:
            same_failed = False
        try:
            hard_problems = search_problems_by_tag(
                tag_key=tag_key, min_tier=hard_min, max_tier=hard_max, exclude_ids=solved_ids,
            )[:HARD_PER_TAG]
        except ProblemSearchError:
            hard_problems = []
            hard_failed = True
        else:
            hard_failed = False

        if same_failed and hard_failed:
            failures += 1
            continue

        problems = same_problems + hard_problems
        problems = list({p["id"]: p for p in problems}.values())

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
    # CF 는 태그별 실패 격리를 하지 않는다. 실패 조건은 프로세스 전역 스냅샷 하나이며
    # 태그와 무관하다. 격리하면 같은 수 MB 다운로드를 태그·밴드 수만큼 반복한다.
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
