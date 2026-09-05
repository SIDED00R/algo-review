import db
import analyzer
from fastapi import APIRouter, HTTPException
from routes.helpers import require_openai_key, require_platform, run_llm
from demo_mode import IS_DEMO, DEMO_REPORT

router = APIRouter()


@router.get("/api/report")
def get_report(platform: str = "boj"):
    # 입력 검증이 환경 검사보다 앞이다 — 반대면 키 없는 서버에서 잘못된 platform 이 500 이 된다.
    # 플랫폼은 stats.py 와 같이 명시 파라미터로 받는다.
    platform = require_platform(platform)
    if IS_DEMO:
        return {"report": DEMO_REPORT}

    require_openai_key()

    # tag_stats 와 history 는 같은 플랫폼이어야 짝이 맞는다 — analyzer.get_cumulative_analysis
    # 가 태그 통계와 최근 풀이 기록을 함께 프롬프트에 넣는다.
    tag_stats = db.get_tag_stats() if platform == "boj" else db.get_cf_tag_stats()
    if not tag_stats:
        # 자료 없음을 400 으로 낸다 — 프론트(report.js)가 이 코드를 안내 문구 조건으로 쓴다.
        raise HTTPException(status_code=400, detail="아직 저장된 기록이 없습니다.")

    # 대기 행은 판정이 없어 프롬프트에 '→ pending' 으로 새어 나간다 — 리포트에서는 제외한다.
    history = [r for r in db.get_review_history(20, platform=platform)
               if r["efficiency"] != db.PENDING_EFFICIENCY][:10]

    report = run_llm("리포트 생성 실패", analyzer.get_cumulative_analysis, tag_stats, history)

    return {"report": report}
