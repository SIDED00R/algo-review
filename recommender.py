from datetime import datetime
from clients import search_problems_by_tag, search_cf_problems_by_tag, get_tag_key_by_name, TIER_NAMES
import db

# 현재 수준: avg-1 ~ avg+2 / 도전 수준: avg+3 ~ avg+8
TIER_RANGE_LOW       = 1   # 현재 수준 하한 오프셋
TIER_RANGE_SAME_HIGH = 2   # 현재 수준 상한 오프셋
TIER_RANGE_HARD_LOW  = 3   # 도전 수준 하한 오프셋
TIER_RANGE_HARD_HIGH = 8   # 도전 수준 상한 오프셋
# 현재 수준 1문제 + 도전 수준 2문제
SAME_PER_TAG = 1
HARD_PER_TAG = 2


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
        count_score   = 1 - (d["solve_count"] / max_count)   # 적게 풀수록 높음
        poor_score    = d["poor_ratio"]                        # AI poor 비율
        recency_score = d["days_since"] / max_days             # 오래됐을수록 높음
        d["weakness_score"] = (
            count_score   * 0.5 +
            poor_score    * 0.3 +
            recency_score * 0.2
        )

    tag_data.sort(key=lambda x: x["weakness_score"], reverse=True)
    return tag_data


def get_weak_tags_scored(top_n: int = 5, platform: str | None = None) -> list[str]:
    tag_data = db.get_tag_weakness_data(platform=platform)
    scored = _score_tags(tag_data)
    return [d["tag"] for d in scored[:top_n]]


def get_recommendations(top_weak_tags: int = 3, platform: str = "boj", extra_exclude: set | None = None) -> list[dict]:
    if platform == "codeforces":
        return _get_cf_recommendations(top_weak_tags, extra_exclude=extra_exclude)

    weak_tags = get_weak_tags_scored(top_weak_tags, platform="boj")
    if not weak_tags:
        return []

    avg_tier = db.get_average_tier()
    same_min = max(1,  int(avg_tier) - TIER_RANGE_LOW)
    same_max = min(30, int(avg_tier) + TIER_RANGE_SAME_HIGH)
    hard_min = min(30, int(avg_tier) + TIER_RANGE_HARD_LOW)
    hard_max = min(30, int(avg_tier) + TIER_RANGE_HARD_HIGH)

    solved_ids = db.get_solved_problem_ids() | (extra_exclude or set())

    recommendations = []
    for tag_name in weak_tags:
        tag_key = get_tag_key_by_name(tag_name)

        same_problems = search_problems_by_tag(
            tag_key=tag_key, min_tier=same_min, max_tier=same_max, exclude_ids=solved_ids,
        )[:SAME_PER_TAG]

        hard_problems = search_problems_by_tag(
            tag_key=tag_key, min_tier=hard_min, max_tier=hard_max, exclude_ids=solved_ids,
        )[:HARD_PER_TAG]

        problems = same_problems + hard_problems

        if problems:
            for p in problems:
                p["url"] = f"https://boj.kr/{p['id']}"
            recommendations.append({
                "tag": tag_name,
                "tag_key": tag_key,
                "problems": problems,
            })

    return recommendations


def _get_cf_recommendations(top_weak_tags: int = 3, extra_exclude: set | None = None) -> list[dict]:
    weak_tags = get_weak_tags_scored(top_weak_tags, platform="codeforces")
    if not weak_tags:
        return []

    avg_rating = db.get_average_cf_rating()
    cf_same_min = max(800,  int(avg_rating) - 200)
    cf_same_max = min(3500, int(avg_rating) + 100)
    cf_hard_min = min(3500, int(avg_rating) + 200)
    cf_hard_max = min(3500, int(avg_rating) + 700)

    exclude_refs = db.get_solved_cf_refs() | (extra_exclude or set())

    recommendations = []
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
