import db
from constants import TIER_NAMES
from fastapi import APIRouter
from routes.helpers import require_platform

router = APIRouter()


@router.get("/api/tier-history")
def get_tier_history():
    return {"history": db.get_tier_history()}


@router.get("/api/stats")
def get_stats(platform: str | None = "boj"):
    platform = require_platform(platform)

    history = db.get_review_history(20, platform=platform)
    total_reviews = db.get_total_review_count(platform)

    if platform == "codeforces":
        avg_rating = db.get_average_cf_rating()
        tag_stats = db.get_cf_tag_stats()
        return {
            "platform": "codeforces",
            "avg_tier_name": f"CF {int(avg_rating)}" if db.has_cf_rating() else "N/A",
            "total_reviews": total_reviews,
            "tag_stats": tag_stats,
            "history": history,
        }

    avg_tier = db.get_average_tier()
    tag_stats = db.get_tag_stats()
    # 등급 있는 기록이 없으면 avg_tier 는 추천용 기본값(10.0)이다 — 그대로 표시하면
    # 기록이 없는 사용자에게 "Silver I" 가 뜬다.
    graded = db.has_graded_tier()
    return {
        "platform": "boj",
        "avg_tier": avg_tier if graded else 0,
        "avg_tier_name": TIER_NAMES.get(int(avg_tier), "N/A") if graded else "N/A",
        "total_reviews": total_reviews,
        "tag_stats": tag_stats,
        "history": history,
    }
