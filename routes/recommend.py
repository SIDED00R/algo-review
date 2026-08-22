import db
import recommender
from clients import ProblemSearchError
from fastapi import APIRouter, Query

from constants import TIER_NAMES
from routes.helpers import require_platform
from demo_mode import IS_DEMO, DEMO_RECOMMENDATIONS, DEMO_RECOMMENDATIONS_BOJ

router = APIRouter()


@router.get("/api/recommend")
def get_recommendations(platform: str = Query("codeforces"), exclude: str = Query("")):
    # 기본값이 codeforces 라 빈 값만 먼저 채우고 검증은 공용 헬퍼에 맡긴다 —
    # 검증 진입점이 갈리면 케이스 정규화·오류 문구가 라우터마다 달라진다.
    platform = require_platform(platform or "codeforces")

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
                # 저장 시 normalize_codeforces_problem_ref 가 대문자화하므로 여기서도 맞춘다 —
                # `?exclude=4a` 가 저장된 `4A` 와 매칭되지 않으면 제외가 조용히 무효가 된다.
                extra_exclude.add(raw.upper())

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
        # 키 집합을 정상 반환과 같게 유지한다 — 분기마다 다르면 프론트가 방어 코드로
        # 메꾸게 되고, 나중에 키 하나를 지워도 아무 데서도 드러나지 않는다.
        return {"avg_tier": avg_tier, "tier_name": tier_name, "tier_range": tier_range,
                "weak_tags": [], "recommendations": [], "platform": platform, "error": ""}

    # 검색 실패를 빈 추천으로 내려보내면 프론트가 '먼저 코드 리뷰를 진행해보세요' 로 안내한다 —
    # themes 응답이 쓰는 error 필드 계약을 그대로 따른다.
    error = ""
    try:
        # 위에서 구한 평균 난이도를 넘긴다 — 넘기지 않으면 recommender 가 같은 요청 안에서
        # reviews 전 행 윈도우 쿼리를 한 번 더 돈다(5만 행에서 490ms).
        recs = recommender.get_recommendations(
            weak_tags[:3], platform=platform, extra_exclude=extra_exclude,
            avg_difficulty=avg_rating if platform == "codeforces" else avg_tier)
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
