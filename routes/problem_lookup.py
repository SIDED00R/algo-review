"""문제 번호 → 뷰어가 열 수 있는 정규 식별자 + 메타. 추천 탭 '문제 직접 열기' 카드가 쓴다.

뷰어(`openProblemModal`)는 정규 ref(`1530D`·`two-sum`)를 전제한다 — 임시 저장 키·LeetCode 채점기·push 본문
매칭이 그 값으로 맞춰진다. 입력(번호·slug·URL)을 정규 ref 로 푸는 일은 리뷰 라우터들이 쓰는
`resolve_problem_info` 가 이미 하므로 그것을 재사용한다(LLM 호출 없음).
"""
import asyncio

from fastapi import APIRouter, HTTPException

from demo_mode import IS_DEMO
from routes.helpers import require_platform
from routes.problem_resolve import resolve_problem_info

router = APIRouter()

# 인앱 뷰어가 있는 플랫폼 — static/js/utils.js PLATFORMS 의 viewer:true 집합과 같다.
_VIEWER_PLATFORMS = ("codeforces", "leetcode")


@router.get("/api/problem/lookup")
async def lookup_problem(platform: str, ref: str = ""):
    platform = require_platform(platform)
    if platform not in _VIEWER_PLATFORMS:
        raise HTTPException(status_code=400,
                            detail="백준은 인앱 뷰어가 없습니다. Codeforces 또는 LeetCode 문제를 입력하세요.")
    if IS_DEMO:
        # 데모 뷰어는 어떤 ref 든 플랫폼별 고정 문제를 보여준다 — 외부 조회 없이 통과시킨다.
        return {"platform": platform, "problem_ref": ref.strip() or "4A", "problem_id": None,
                "title": "", "tier_name": "", "url": None}
    # 동기 requests(스냅샷 수 MB·30초) — 이벤트 루프를 막지 않게 스레드로 뺀다.
    # 빈 입력·형식 오류·없는 문제는 400, 상류 장애는 502 로 resolve_problem_info 가 매핑한다.
    info = await asyncio.to_thread(resolve_problem_info, platform, None, ref)
    return {
        "platform": platform,
        "problem_ref": info["problem_ref"],
        "problem_id": info.get("id") or None,
        "title": info["title"],
        "tier_name": info["tier_name"],
        "url": info.get("url"),
    }
