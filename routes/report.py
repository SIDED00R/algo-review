import db
import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from demo_mode import IS_DEMO, DEMO_REPORT

router = APIRouter()


@router.get("/api/report")
def get_report():
    if IS_DEMO:
        return {"report": DEMO_REPORT}

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    # tag_stats 는 BOJ 첫 제출에만 집계된다 — CF 기록만 있는 사용자를 위해 stats.py 와 같은 방식으로
    # 플랫폼을 분기한다. history 도 같은 플랫폼으로 걸러야 tag_stats 와 짝이 맞는다(analyzer.py 가
    # 태그 통계와 최근 풀이 기록을 함께 프롬프트에 넣는다).
    platform = "boj"
    tag_stats = db.get_tag_stats()
    if not tag_stats:
        tag_stats = db.get_cf_tag_stats()
        platform = "codeforces"

    # 대기 행은 판정이 없어 프롬프트에 '→ pending' 으로 새어 나간다 — 리포트에서는 제외한다.
    history = [r for r in db.get_review_history(20, platform=platform)
               if r["efficiency"] != db.PENDING_EFFICIENCY][:10]

    if not tag_stats:
        raise HTTPException(status_code=400, detail="아직 저장된 기록이 없습니다.")

    try:
        report = analyzer.get_cumulative_analysis(tag_stats, history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 생성 실패: {e}")

    return {"report": report}
