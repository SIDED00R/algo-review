import db
from fastapi import APIRouter
from routes.helpers import average_difficulty, require_platform

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
        _, _, avg_tier_name = average_difficulty("codeforces")
        tag_stats = db.get_cf_tag_stats()
        return {
            "platform": "codeforces",
            "avg_tier_name": avg_tier_name,
            "total_reviews": total_reviews,
            "tag_stats": tag_stats,
            "history": history,
        }

    avg_tier, graded, avg_tier_name = average_difficulty("boj")
    tag_stats = db.get_tag_stats()
    return {
        "platform": "boj",
        # 등급 있는 기록이 없으면 avg_tier 는 추천용 기본값(10.0)이다 — 그대로 내보내면
        # 기록이 없는 사용자에게 "Silver I" 가 뜬다.
        "avg_tier": avg_tier if graded else 0,
        "avg_tier_name": avg_tier_name,
        "total_reviews": total_reviews,
        "tag_stats": tag_stats,
        "history": history,
    }
