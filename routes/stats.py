import db
import clients as api_client
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/tier-history")
def get_tier_history():
    return {"history": db.get_tier_history()}


@router.get("/api/stats")
def get_stats(platform: str | None = "boj"):
    platform = (platform or "boj").strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다.")

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
