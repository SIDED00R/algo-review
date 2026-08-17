import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from routes.models import _normalize_platform

router = APIRouter()


@router.get("/api/tier-history")
def get_tier_history():
    return {"history": db.get_tier_history()}


@router.get("/api/stats")
def get_stats(platform: str | None = "boj"):
    try:
        platform = _normalize_platform(platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    history = db.get_review_history(20, platform=platform)
    total_reviews = db.get_total_review_count(platform)

    if platform == "codeforces":
        avg_rating = db.get_average_cf_rating()
        tag_stats = db.get_cf_tag_stats()
        return {
            "platform": "codeforces",
            "avg_tier_name": f"CF {int(avg_rating)}",
            "total_reviews": total_reviews,
            "tag_stats": tag_stats,
            "history": history,
        }

    avg_tier = db.get_average_tier()
    tag_stats = db.get_tag_stats()
    return {
        "platform": "boj",
        "avg_tier": avg_tier,
        "avg_tier_name": api_client.TIER_NAMES.get(int(avg_tier), "N/A"),
        "total_reviews": total_reviews,
        "tag_stats": tag_stats,
        "history": history,
    }
