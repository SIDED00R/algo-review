"""/api/problem/lc — 본문 HTML 번역·유료 문제·오류 매핑·캐시 공유."""
import pytest

import clients as api_client
from clients import ProblemNotFound, UpstreamUnavailable
from routes import problem_cache
from routes import problem_leetcode as lc_route

_RAW = {
    "title": "Two Sum", "problem_id": 1, "difficulty": "Easy", "tier": 1, "category": "Algorithms",
    "is_paid_only": False, "content_html": "<p>hi</p>", "tags": ["Array"],
    "url": "https://leetcode.com/problems/two-sum/",
}


@pytest.fixture(autouse=True)
def clean_cache():
    problem_cache._CACHE.clear()
    problem_cache._IN_FLIGHT.clear()
    yield
    problem_cache._CACHE.clear()
    problem_cache._IN_FLIGHT.clear()


def test_viewer_translates_html_and_caches_by_normalized_slug(minimal_app, monkeypatch):
    calls = []
    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: calls.append(slug) or dict(_RAW))

    def _translate(text, title, **kwargs):
        assert kwargs == {"source": "LeetCode", "html": True}, kwargs
        return f"[ko]{text}"

    monkeypatch.setattr(lc_route, "translate_statement", _translate)
    client = minimal_app(lc_route.router)

    first = client.get("/api/problem/lc/Two-Sum").json()
    assert first["content_html_ko"] == "[ko]<p>hi</p>"
    assert first["translated"] is True
    assert (first["difficulty"], first["category"], first["problem_id"]) == ("Easy", "Algorithms", 1)
    assert "samples" not in first and "harness" not in first, \
        "메타데이터 없는 응답에는 예제가 없다 — 프런트는 samples 유무로 실행 영역을 숨긴다"
    assert client.get("/api/problem/lc/two-sum").json() == first
    assert calls == ["two-sum"], "정규화된 slug 하나로 한 번만 수집해야 한다"


def test_algorithm_problem_carries_samples_and_python_harness(minimal_app, monkeypatch):
    raw = dict(_RAW,
               content_html="<pre>Input: nums = [2,7,11,15], target = 9\nOutput: [0,1]</pre>",
               example_testcases="[2,7,11,15]\n9",
               meta_data='{"name":"twoSum","params":[{"name":"nums","type":"integer[]"},'
                         '{"name":"target","type":"integer"}],"return":{"type":"integer[]"}}')
    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: raw)
    # 예제는 번역 전 원문에서 뽑는다 — 번역이 Output 줄을 한국어로 바꿔도 기대 출력은 남아야 한다.
    monkeypatch.setattr(lc_route, "translate_statement",
                        lambda text, title, **kw: text.replace("Output:", "출력:"))
    body = minimal_app(lc_route.router).get("/api/problem/lc/two-sum").json()
    assert body["samples"] == [{"input": "[2,7,11,15]\n9", "output": "[0,1]"}]
    assert body["harness"]["prelude"].startswith("from typing import *")
    assert "_LC_NAME = 'twoSum'" in body["harness"]["epilogue"]
    assert "출력:" in body["content_html_ko"]


def test_paid_problem_skips_translation_and_is_cached_permanently(minimal_app, monkeypatch):
    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: dict(_RAW, is_paid_only=True, content_html=""))
    monkeypatch.setattr(lc_route, "translate_statement", lambda *a, **k: pytest.fail("유료 문제인데 번역을 불렀다"))
    body = minimal_app(lc_route.router).get("/api/problem/lc/x").json()
    assert body["is_paid_only"] and body["content_html_ko"] == "" and body["translated"] is False
    assert problem_cache._CACHE["lc:x"]["expires"] is None


def test_translation_failure_returns_the_original_with_a_short_ttl(minimal_app, monkeypatch):
    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: dict(_RAW))
    monkeypatch.setattr(lc_route, "translate_statement", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    body = minimal_app(lc_route.router).get("/api/problem/lc/two-sum").json()
    assert body["content_html_ko"] == "<p>hi</p>" and body["translated"] is False
    assert problem_cache._CACHE["lc:two-sum"]["expires"] is not None


def test_error_mapping(minimal_app, monkeypatch):
    client = minimal_app(lc_route.router)
    assert client.get("/api/problem/lc/Bad Slug!").status_code == 400

    monkeypatch.setattr(api_client, "scrape_lc_problem", lambda slug: (_ for _ in ()).throw(ProblemNotFound("없음")))
    assert client.get("/api/problem/lc/nope").status_code == 404

    monkeypatch.setattr(api_client, "scrape_lc_problem",
                        lambda slug: (_ for _ in ()).throw(UpstreamUnavailable("LeetCode API 오류 (HTTP 500)")))
    assert client.get("/api/problem/lc/nope2").status_code == 502
    assert problem_cache._IN_FLIGHT == {}
