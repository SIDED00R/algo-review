import db
import clients as api_client
import recommender
from recommender import CF_RANGE_LOW, CF_RANGE_HARD_HIGH
from fastapi import APIRouter, HTTPException, Query
from demo_mode import IS_DEMO, DEMO_RECOMMENDATIONS, DEMO_RECOMMENDATIONS_BOJ

router = APIRouter()


@router.get("/api/recommend")
def get_recommendations(platform: str = Query("codeforces"), exclude: str = Query("")):
    platform = (platform or "codeforces").strip().lower()
    if platform not in {"boj", "codeforces"}:
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
        tier_range = f"CF {max(800, int(avg_rating) - CF_RANGE_LOW)} ~ CF {min(3500, int(avg_rating) + CF_RANGE_HARD_HIGH)}"
    else:
        avg_tier = db.get_average_tier()
        tier_name = api_client.TIER_NAMES.get(int(avg_tier), "N/A")
        tier_range = recommender.tier_range_description(avg_tier)

    weak_tags = recommender.get_weak_tags_scored(5, platform=platform)

    if not weak_tags:
        return {"avg_tier": avg_tier, "tier_name": tier_name,
                "weak_tags": [], "recommendations": [], "platform": platform}

    recs = recommender.get_recommendations(top_weak_tags=3, platform=platform, extra_exclude=extra_exclude,
                                           weak_tags=weak_tags[:3])

    return {
        "avg_tier": avg_tier,
        "tier_name": tier_name,
        "tier_range": tier_range,
        "weak_tags": weak_tags,
        "recommendations": recs,
        "platform": platform,
    }
