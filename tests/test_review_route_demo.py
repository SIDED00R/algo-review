"""데모 모드 리뷰 라우트 — 빈 코드 검증이 데모 조기 반환보다 먼저 와야 한다(회귀).

수정 전에는 `if IS_DEMO:` 조기 반환이 빈 코드 400 검사보다 앞에 있어, 데모에서
빈 코드({"code": "   "})를 보내도 200 + 리뷰 행 저장으로 이어졌다.
"""
import pytest

import db
from routes import review

_BODY = {"platform": "boj", "problem_id": 1000, "code": "print(1)", "language": "Python 3"}


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(review, "IS_DEMO", True)
    return minimal_app(review.router)


def test_demo_mode_rejects_empty_code(minimal_client):
    r = minimal_client.post("/api/review", json={**_BODY, "code": "   "})
    assert r.status_code == 400


def test_demo_mode_returns_review_for_nonempty_code(minimal_client):
    r = minimal_client.post("/api/review", json=_BODY)
    assert r.status_code == 200

    # 데모 경로도 language 를 저장에 전달해야 한다 — 안 넘기면 저장된 행의 language 가
    # 항상 "" 이 되고, rereview 가 파일명을 재현할 수 없다며 재업로드를 영구 거부한다.
    saved = db.get_reviews_by_problem("boj", "1929")  # DEMO_PROBLEM_INFO 의 problem_ref
    assert saved[0]["language"] == "Python 3"
