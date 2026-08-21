import db
import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from routes.helpers import require_platform, upstream_failure
from demo_mode import IS_DEMO, DEMO_REPORT

router = APIRouter()


@router.get("/api/report")
def get_report(platform: str = "boj"):
    if IS_DEMO:
        return {"report": DEMO_REPORT}

    # 입력 검증이 환경 검사보다 앞이다 — 순서가 반대면 키 없는 서버에서 잘못된 platform 이
    # 400 이 아니라 500 을 받는다(routes/solved.py 는 이 순서다).
    # 플랫폼은 stats.py 와 같이 **명시 파라미터**로 받는다. 예전에는 "BOJ 태그 통계가 비면
    # CF" 라는 데이터 공백 추론이었는데, BOJ 기록이 하나라도 있으면 CF 리포트를 영구히 볼
    # 수 없었다(리포트 탭에 토글이 없어 우회 경로도 없었다).
    platform = require_platform(platform)

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    # tag_stats 와 history 는 같은 플랫폼이어야 짝이 맞는다 — analyzer.get_cumulative_analysis
    # 가 태그 통계와 최근 풀이 기록을 함께 프롬프트에 넣는다.
    tag_stats = db.get_tag_stats() if platform == "boj" else db.get_cf_tag_stats()
    if not tag_stats:
        # 기록이 없으면 아래 history 조회는 헛돈다 — 먼저 거절한다.
        raise HTTPException(status_code=400, detail="아직 저장된 기록이 없습니다.")

    # 대기 행은 판정이 없어 프롬프트에 '→ pending' 으로 새어 나간다 — 리포트에서는 제외한다.
    history = [r for r in db.get_review_history(20, platform=platform)
               if r["efficiency"] != db.PENDING_EFFICIENCY][:10]

    try:
        report = analyzer.get_cumulative_analysis(tag_stats, history)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise upstream_failure("리포트 생성 실패", e)

    return {"report": report}
