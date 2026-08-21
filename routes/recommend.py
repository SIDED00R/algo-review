import db
import recommender
from clients import ProblemSearchError
from fastapi import APIRouter, HTTPException, Query

from constants import TIER_NAMES, is_supported_platform, normalize_platform
from demo_mode import IS_DEMO, DEMO_RECOMMENDATIONS, DEMO_RECOMMENDATIONS_BOJ

router = APIRouter()


@router.get("/api/recommend")
def get_recommendations(platform: str = Query("codeforces"), exclude: str = Query("")):
    platform = normalize_platform(platform, default="codeforces")
    if not is_supported_platform(platform):
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다.")

    if IS_DEMO:
        demo = DEMO_RECOMMENDATIONS_BOJ if platform == "boj" else DEMO_RECOMMENDATIONS
        return {**demo, "platform": platform}

    extra_exclude: set = set()
    if exclude:
        for raw in exclude.split(","):
            raw = raw.strip()
            if not raw:
                continue
            if platform == "boj":
                try:
                    extra_exclude.add(int(raw))
                except ValueError:
                    pass
            else:
                extra_exclude.add(raw)

    if platform == "codeforces":
        avg_rating = db.get_average_cf_rating()
        avg_tier = 0
        tier_name = f"CF {int(avg_rating)}" if avg_rating != 1200.0 or db.get_solved_cf_refs() else "N/A"
        tier_range = recommender.cf_rating_range_description(avg_rating)
    else:
        avg_tier = db.get_average_tier()
        tier_name = TIER_NAMES.get(int(avg_tier), "N/A")
        tier_range = recommender.tier_range_description(avg_tier)

    weak_tags = recommender.get_weak_tags_scored(5, platform=platform)

    if not weak_tags:
        return {"avg_tier": avg_tier, "tier_name": tier_name,
                "weak_tags": [], "recommendations": [], "platform": platform}

    # 검색 실패를 빈 추천으로 내려보내면 프론트가 "아직 추천 데이터가 없습니다. 먼저 코드
    # 리뷰를 몇 개 진행해보세요." 로 **사용자를 탓한다** — 평균 티어와 취약 태그가 같은
    # 응답에 채워져 있는데도. themes 응답이 이미 쓰는 error 필드 계약을 그대로 따른다. (#113)
    error = ""
    try:
        recs = recommender.get_recommendations(weak_tags[:3], platform=platform,
                                               extra_exclude=extra_exclude)
    except ProblemSearchError as e:
        recs, error = [], str(e)

    return {
        "avg_tier": avg_tier,
        "tier_name": tier_name,
        "tier_range": tier_range,
        "weak_tags": weak_tags,
        "recommendations": recs,
        "platform": platform,
        "error": error,
    }
