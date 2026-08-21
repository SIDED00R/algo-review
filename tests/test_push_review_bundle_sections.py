"""push_review_bundle 의 require_sections 계약 (회귀).

수집이 실패했을 때:
- 갱신 경로(require_sections=True, 기본값)는 502 로 막고 GitHub push 를 아예 시도하지 않는다
  — 이미 올라간 문제 설명을 본문 없이 덮어써 지우지 않기 위해서다.
- 아직 문서가 없는 최초 등록 경로(require_sections=False)는 본문 없이도 정상 저장된다.

**두 플랫폼을 모두 돌린다.** 예전에는 CF 만 덮었고, 그 사이 BOJ 의 수집 함수는 실패에도
빈 문자열 dict 를 반환해 `sections` 판정이 BOJ 에서 영원히 거짓이었다 — 가드가 CF 전용인 채로
테스트는 초록이었다. 실패 표현이 None 이든 빈 섹션이든 결과가 같아야 한다.
"""
import pytest
from fastapi import HTTPException

from routes import helpers

_CF_KW = dict(
    platform="codeforces", problem_ref="4A", title="Watermelon",
    tier_name="Codeforces 800", tags=["math"], language="Python 3",
    code="print(1)",
)
_BOJ_KW = dict(
    platform="boj", problem_ref="1000", title="A+B",
    tier_name="Bronze V", tags=["arithmetic"], language="Python 3",
    code="print(1)",
)

# (라벨, push_review_bundle 인자, 수집 함수 이름, 실패 시 그 함수의 반환값, 기대 폴더)
_CASES = [
    ("cf-none", _CF_KW, "get_cf_problem_sections", None, "Codeforces/4A. Watermelon"),
    ("boj-none", _BOJ_KW, "get_boj_problem_sections", None, "백준/Bronze/1000번. A+B"),
    # 수집기가 실패를 빈 섹션으로 표현해도 같은 결과여야 한다.
    ("boj-empty", _BOJ_KW, "get_boj_problem_sections",
     {"description": "", "input": "", "output": ""}, "백준/Bronze/1000번. A+B"),
    ("cf-empty", _CF_KW, "get_cf_problem_sections",
     {"description": "", "input": "", "output": ""}, "Codeforces/4A. Watermelon"),
]
_IDS = [c[0] for c in _CASES]


def _patch(monkeypatch, fetcher, failure_value):
    monkeypatch.setattr(helpers.api_client, fetcher, lambda *a, **k: failure_value)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)
    return calls


@pytest.mark.parametrize("_label,kw,fetcher,failure_value,_folder", _CASES, ids=_IDS)
def test_scrape_failure_blocks_update_path(monkeypatch, _label, kw, fetcher, failure_value, _folder):
    calls = _patch(monkeypatch, fetcher, failure_value)

    with pytest.raises(HTTPException) as exc_info:
        helpers.push_review_bundle("owner/repo", "token", **kw)  # require_sections 기본값 True

    assert exc_info.value.status_code == 502
    assert calls == []  # GitHub push 자체가 시도되면 안 된다


@pytest.mark.parametrize("_label,kw,fetcher,failure_value,folder", _CASES, ids=_IDS)
def test_scrape_failure_allows_first_time_registration(monkeypatch, _label, kw, fetcher,
                                                       failure_value, folder):
    calls = _patch(monkeypatch, fetcher, failure_value)

    result = helpers.push_review_bundle("owner/repo", "token", require_sections=False, **kw)

    assert result == folder
    assert len(calls) == 1  # 본문 없이도 push 는 진행된다


@pytest.mark.parametrize("_label,kw,fetcher,_failure,_folder", _CASES, ids=_IDS)
def test_stored_description_skips_scraping(monkeypatch, _label, kw, fetcher, _failure, _folder):
    """호출자가 본문을 주면 수집을 아예 타지 않는다 — 저장된 problem_statement 로 재푸시하는 경로."""
    def _fail(*a, **k):
        pytest.fail(f"{fetcher} 가 호출되면 안 된다 — 호출자가 본문을 넘겼다")

    monkeypatch.setattr(helpers.api_client, fetcher, _fail)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)

    helpers.push_review_bundle("owner/repo", "token", description="【문제】저장된 본문", **kw)

    assert len(calls) == 1
    readme = next(f["content"] for f in calls[0][0][2] if f["path"].endswith("README.md"))
    assert "저장된 본문" in readme
