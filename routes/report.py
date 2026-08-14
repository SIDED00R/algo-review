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

    tag_stats = db.get_tag_stats()
    # 대기 행은 판정이 없어 프롬프트에 '→ pending' 으로 새어 나간다 — 리포트에서는 제외한다.
    history = [r for r in db.get_review_history(20)
               if r["efficiency"] != db.PENDING_EFFICIENCY][:10]

    if not tag_stats:
        raise HTTPException(status_code=400, detail="아직 저장된 기록이 없습니다.")

    try:
        report = analyzer.get_cumulative_analysis(tag_stats, history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 생성 실패: {e}")

    return {"report": report}
