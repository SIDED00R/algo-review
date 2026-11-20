"""문제 번호 → 뷰어가 열 수 있는 정규 식별자 + 메타. 추천 탭 '문제 직접 열기' 카드가 쓴다.

뷰어(`openProblemModal`)는 정규 ref(`1000`·`1530D`·`two-sum`)를 전제한다 — 임시 저장 키·LeetCode 채점기·
push 본문 매칭이 그 값으로 맞춰진다. CF·LeetCode 입력(번호·slug·URL)을 정규 ref 로 푸는 일은 리뷰 라우터들이
쓰는 `resolve_problem_info` 를 재사용하고, 백준은 solved.ac 를 직접 조회한다(LLM 호출 없음).
"""
import asyncio

import requests
from fastapi import APIRouter, HTTPException

import clients as api_client
from demo_mode import IS_DEMO
from routes.helpers import require_platform, require_problem_ref, upstream_failure
from routes.problem_resolve import resolve_problem_info

router = APIRouter()


def _lookup_boj(ref: str) -> dict:
    """백준 번호 → solved.ac 메타. DB 를 읽지 않는다. 없는 문제는 400, solved.ac 장애는 502."""
    ref = require_problem_ref("boj", ref)
    try:
        info = api_client.get_problem_info(int(ref))
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise HTTPException(status_code=400, detail=f"백준에 없는 문제입니다: {ref}") from None
        raise upstream_failure("solved.ac 문제 조회 실패", e)
    except Exception as e:
        raise upstream_failure("solved.ac 문제 조회 실패", e)
    return {**info, "problem_ref": str(info["id"]), "url": api_client.get_problem_url("boj", info["id"])}


@router.get("/api/problem/lookup")
async def lookup_problem(platform: str, ref: str = ""):
    platform = require_platform(platform)
    if IS_DEMO:
        # 데모 뷰어는 어떤 ref 든 플랫폼별 고정 문제를 보여준다 — 외부 조회 없이 통과시킨다.
        return {"platform": platform, "problem_ref": ref.strip() or "4A", "problem_id": None,
                "title": "", "tier_name": "", "url": None}
    # 동기 requests(스냅샷 수 MB·30초) — 이벤트 루프를 막지 않게 스레드로 뺀다.
    # 빈 입력·형식 오류·없는 문제는 400, 상류 장애는 502 다.
    if platform == "boj":
        info = await asyncio.to_thread(_lookup_boj, ref)
    else:
        info = await asyncio.to_thread(resolve_problem_info, platform, None, ref)
    return {
        "platform": platform,
        "problem_ref": info["problem_ref"],
        "problem_id": info.get("id") or None,
        "title": info["title"],
        "tier_name": info["tier_name"],
        "url": info.get("url"),
    }
