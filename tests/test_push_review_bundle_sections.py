"""push_review_bundle 의 require_sections 계약 (회귀).

CF 스크래핑이 실패(None)했을 때:
- 갱신 경로(require_sections=True, 기본값)는 502 로 막고 GitHub push 를 아예 시도하지 않는다
  — 이미 올라간 문제 설명을 본문 없이 덮어써 지우지 않기 위해서다.
- 아직 문서가 없는 최초 등록 경로(require_sections=False)는 본문 없이도 정상 저장된다.
"""
import pytest
from fastapi import HTTPException

from routes import helpers

_KW = dict(
    platform="codeforces", problem_ref="4A", title="Watermelon",
    tier_name="Codeforces 800", tags=["math"], language="Python 3",
    code="print(1)",
)


def _patch(monkeypatch):
    monkeypatch.setattr(helpers.api_client, "get_cf_problem_sections", lambda ref: None)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)
    return calls


def test_scrape_failure_blocks_update_path(monkeypatch):
    calls = _patch(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        helpers.push_review_bundle("owner/repo", "token", **_KW)  # require_sections 기본값 True

    assert exc_info.value.status_code == 502
    assert calls == []  # GitHub push 자체가 시도되면 안 된다


def test_scrape_failure_allows_first_time_registration(monkeypatch):
    calls = _patch(monkeypatch)

    folder = helpers.push_review_bundle("owner/repo", "token", require_sections=False, **_KW)

    assert folder == "Codeforces/4A. Watermelon"
    assert len(calls) == 1  # 본문 없이도 push 는 진행된다
