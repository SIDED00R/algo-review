"""LLM 이 null 을 준 필드가 저장 경로를 어떻게 통과하는지.

문자열 필드와 리스트 필드는 **실패 양상이 다르다**.
- 문자열: NOT NULL 컬럼에 None → IntegrityError → 롤백. 이미 과금된 응답과 tag_stats
  첫 집계가 함께 사라진다. 요란하게 실패하므로 눈에 띈다.
- 리스트: `json.dumps(None)` 은 예외 없이 문자열 `"null"` 을 만들어 **조용히** 통과하고,
  읽을 때 `json.loads("null")` → None 이 되어 API 가 `"strengths": null` 을 내보낸다.

`.get(key, default)` 는 키가 있고 값이 None 이면 default 를 적용하지 않는다 — 이것이
두 경우의 공통 원인이다. 정규화는 생산자(analyzer) 한 곳에서 끝내고, 저장 함수 둘은
dict 를 직접 받는 공개 경로라 각자 한 번 더 막는다.
"""
import json

import pytest
from sqlalchemy import select

import analyzer
import db
from db.connection import session_scope
from db.models import Review

_NULLED = {
    "efficiency": None, "complexity": None, "better_algorithm": None,
    "feedback": None, "strengths": None, "weaknesses": None,
}
_BASE = dict(problem_id=1000, title="A+B", tier=1, tags=["math"],
             code="print(1)", platform="boj", problem_ref="1000",
             tier_name="Bronze V", language="Python 3")


def test_normalize_turns_null_lists_into_empty_lists():
    out = analyzer.normalize_review_result(dict(_NULLED))
    assert out["strengths"] == [] and out["weaknesses"] == []
    assert out["complexity"] == "" and out["better_algorithm"] == "" and out["feedback"] == ""
    assert out["efficiency"] == "ok"


@pytest.mark.parametrize("junk", [None, "not a list", 42, {"a": 1}])
def test_normalize_rejects_non_list_values(junk):
    out = analyzer.normalize_review_result({"strengths": junk, "weaknesses": junk})
    assert out["strengths"] == [] and out["weaknesses"] == []


def test_update_pending_review_never_stores_the_string_null():
    """대기 행 채우기는 두 번째 저장 경로다 — save_review 만 막으면 여기가 뚫린다."""
    db.save_review(**_BASE, feedback="", efficiency=db.PENDING_EFFICIENCY)

    target = db.get_reviews_by_problem("boj", "1000")[0]["id"]
    assert db.update_pending_review("boj", "1000", dict(_NULLED, efficiency="good"),
                                    review_id=target)

    row = db.get_reviews_by_problem("boj", "1000")[0]
    assert row["strengths"] == [] and row["weaknesses"] == []


def test_saved_json_columns_are_never_the_literal_null_text():
    """API 응답이 아니라 컬럼 값을 직접 본다 — 정규화가 읽기 쪽에만 있으면 통과해 버린다."""
    kwargs = dict(_BASE, tags=None)
    db.save_review(**kwargs, feedback="f", efficiency="good",
                   strengths=None, weaknesses=None)

    with session_scope() as session:
        stored = session.execute(
            select(Review.strengths, Review.weaknesses, Review.tags)).all()
    for row in stored:
        for value in row:
            assert value != "null", "json.dumps(None) 이 그대로 저장됐다"
            assert json.loads(value) == []
