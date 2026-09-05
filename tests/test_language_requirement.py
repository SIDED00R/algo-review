"""제출 언어를 요구하는 세 엔드포인트.

언어를 모르면 get_file_extension 이 `.txt` 를 주고, 저장소에 `1000.txt` 로 커밋된 풀이는
rereview 가 "저장된 언어 정보가 없어 파일명을 재현할 수 없습니다" 로 **영구 거부**한다.

세 엔드포인트가 같은 하류 제약을 공유하므로 셋 다 막는다. 프론트의 "자동 감지" 옵션은
detectLanguage 가 미인식 코드에 '' 를 반환하므로 빈 값이 실제로 도달한다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from config import settings
from routes import github_push, pending_review, review

_CODE = {"platform": "boj", "problem_id": 1000, "code": "print(1)"}
_PUSH = {"platform": "boj", "problem_ref": "1000", "title": "A+B",
         "tier_name": "Bronze V", "code": "print(1)"}


def _client(module):
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


@pytest.mark.parametrize("language", ["", "   "])
@pytest.mark.parametrize("module,path,payload", [
    (review, "/api/review", _CODE),
    (pending_review, "/api/review/pending", _CODE),
    (github_push, "/api/push-review", _PUSH),
])
def test_blank_language_is_rejected(monkeypatch, module, path, payload, language):
    monkeypatch.setattr(module, "IS_DEMO", False)
    r = _client(module).post(path, json={**payload, "language": language})
    assert r.status_code == 400
    assert "언어를 선택해주세요" in r.json()["detail"]


@pytest.mark.parametrize("module,path,payload", [
    (review, "/api/review", _CODE),
    (pending_review, "/api/review/pending", _CODE),
    (github_push, "/api/push-review", _PUSH),
])
def test_missing_language_field_is_rejected(monkeypatch, module, path, payload):
    """모델 기본값이 "" 이라 필드를 아예 빼도 같은 경로로 들어온다."""
    monkeypatch.setattr(module, "IS_DEMO", False)
    r = _client(module).post(path, json=payload)
    assert r.status_code == 400


def test_language_check_runs_before_any_external_work(monkeypatch):
    """거절이 늦으면 이미 유료 호출·스크래핑을 한 뒤가 된다."""
    called = []
    monkeypatch.setattr(review, "IS_DEMO", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(review, "resolve_problem_info",
                        lambda *a, **k: called.append("resolve") or {})

    assert _client(review).post("/api/review", json=_CODE).status_code == 400
    assert called == []


def test_a_real_language_still_gets_through(monkeypatch):
    """거절 규칙이 정상 경로까지 막지 않는지 — 가드는 빈 값만 걸러야 한다."""
    monkeypatch.setattr(pending_review, "IS_DEMO", True)
    info = pending_review.DEMO_PROBLEM_INFO
    r = _client(pending_review).post(
        "/api/review/pending", json={**_CODE, "language": "Python 3"})
    assert r.status_code == 200
    saved = db.get_reviews_by_problem(info["platform"], info["problem_ref"])
    assert saved and saved[0]["language"] == "Python 3"
