"""/api/report 의 플랫폼 분기.

tag_stats() 는 BOJ 첫 제출에만 집계되므로, 플랫폼을 정하지 않으면 CF 리뷰만 있는
사용자가 "아직 저장된 기록이 없습니다"(400)를 받는다.

플랫폼은 stats.py 와 같이 **명시 파라미터**로 받는다. "BOJ 태그 통계가 비면 CF" 같은
데이터 공백 추론으로 정하면 두 플랫폼을 함께 쓰는 사용자가 CF 리포트를 볼 수 없다 —
리포트 탭에 토글이 있어도 서버가 그 값을 보지 않으면 소용이 없다.
"""
import pytest

import db
from routes import report

_CF_KW = dict(
    problem_id=0, title="Watermelon", tier=0, tags=["math"],
    code="print(1)", feedback="f", efficiency="good",
    platform="codeforces", problem_ref="4A", tier_name="Codeforces 800",
)
_BOJ_KW = dict(
    problem_id=1000, title="A+B", tier=1, tags=["math"],
    code="print(1)", feedback="f", efficiency="good",
    platform="boj", problem_ref="1000", tier_name="Bronze V",
)


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(report.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(report.analyzer, "get_cumulative_analysis", lambda *a, **k: "리포트 본문")
    return minimal_app(report.router)


def test_cf_only_history_is_not_400(minimal_client):
    db.save_review(**_CF_KW)

    r = minimal_client.get("/api/report?platform=codeforces")

    assert r.status_code == 200
    assert r.json()["report"] == "리포트 본문"


def test_cf_report_is_reachable_even_when_boj_records_exist(minimal_client):
    """두 플랫폼을 함께 쓰는 조합 — 이 경우가 실사용의 기본형이다.

    "BOJ 태그 통계가 비면 CF" 같은 데이터 공백 추론으로 분기하면, BOJ 기록이 하나라도
    있는 사용자는 CF 리포트를 볼 수 없다.
    """
    db.save_review(**_BOJ_KW)
    db.save_review(**_CF_KW)

    assert minimal_client.get("/api/report?platform=codeforces").status_code == 200
    assert minimal_client.get("/api/report?platform=boj").status_code == 200


def test_default_platform_is_boj(minimal_client):
    db.save_review(**_BOJ_KW)
    assert minimal_client.get("/api/report").status_code == 200


def test_empty_platform_is_rejected_before_touching_history(minimal_client):
    """기록이 없으면 history 조회 전에 거절한다 — 헛도는 DB 왕복을 만들지 않는다."""
    db.save_review(**_CF_KW)
    r = minimal_client.get("/api/report?platform=boj")
    assert r.status_code == 400
    assert "기록이 없습니다" in r.json()["detail"]


def test_unknown_platform_is_rejected(minimal_client):
    # stats/history 와 같은 400 이다 — require_platform 이 ValueError 를 400 으로 바꾼다
    # (validate_platform 을 라우터에서 그대로 쓰면 500 이 된다).
    assert minimal_client.get("/api/report?platform=leetcode").status_code == 400
