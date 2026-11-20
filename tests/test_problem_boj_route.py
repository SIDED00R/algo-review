"""/api/problem/boj — 응답 모양·오류 매핑·캐시 공유·데모. 수집은 clients 대역으로 끊는다."""
import pytest
import requests

import clients as api_client
from clients import ProblemNotFound
from demo_mode import DEMO_BOJ_PROBLEM
from routes import problem_boj as boj_route
from routes import problem_cache

_RAW = {
    "problem_id": 1000, "title": "A+B", "time_limit": "2 초", "memory_limit": "128 MB",
    "sections_html": {"statement": "<p>두 정수 A와 B</p>", "input": "<p>A B</p>", "output": "<p>A+B</p>",
                      "limit": "", "hint": ""},
    "sections_text": {"statement": "두 정수 A와 B", "input": "A B", "output": "A+B", "limit": "", "hint": ""},
    "samples": [{"input": "1 2", "output": "3"}],
    "url": "https://www.acmicpc.net/problem/1000",
}


@pytest.fixture(autouse=True)
def clean_cache():
    problem_cache._CACHE.clear()
    problem_cache._IN_FLIGHT.clear()
    yield
    problem_cache._CACHE.clear()
    problem_cache._IN_FLIGHT.clear()


@pytest.fixture
def client(minimal_app):
    return minimal_app(boj_route.router)


def test_viewer_response_has_html_and_text_sections_and_is_cached_by_number(client, monkeypatch):
    calls = []
    monkeypatch.setattr(api_client, "scrape_boj_problem", lambda pid: calls.append(pid) or dict(_RAW))

    first = client.get("/api/problem/boj/1000").json()

    assert first == {
        "problem_id": 1000, "title": "A+B", "time_limit": "2 초", "memory_limit": "128 MB",
        "statement_sections_html": _RAW["sections_html"],
        "statement_sections_ko": _RAW["sections_text"],
        "samples": [{"input": "1 2", "output": "3"}],
        "url": "https://www.acmicpc.net/problem/1000",
    }
    assert client.get("/api/problem/boj/01000").json() == first
    assert calls == [1000], "같은 번호는 한 번만 수집해야 한다"


@pytest.mark.parametrize("ref", ["abc", "12a", "-1", " "])
def test_non_numeric_ref_is_a_400_without_scraping(client, monkeypatch, ref):
    monkeypatch.setattr(api_client, "scrape_boj_problem", lambda pid: pytest.fail("형식 오류를 수집했다"))

    resp = client.get(f"/api/problem/boj/{ref}")

    assert resp.status_code == 400
    assert "숫자" in resp.json()["detail"]


def test_missing_problem_is_404_and_outage_is_502_and_neither_is_cached(client, monkeypatch):
    def missing(pid):
        raise ProblemNotFound(f"백준에 없는 문제입니다: {pid}")

    monkeypatch.setattr(api_client, "scrape_boj_problem", missing)
    resp = client.get("/api/problem/boj/999999")
    assert resp.status_code == 404
    assert "없는 문제" in resp.json()["detail"]

    def down(pid):
        raise requests.ConnectionError("acmicpc.net unreachable")

    monkeypatch.setattr(api_client, "scrape_boj_problem", down)
    resp = client.get("/api/problem/boj/1000")
    assert resp.status_code == 502
    assert "ConnectionError" in resp.json()["detail"]
    assert problem_cache._CACHE == {}


def test_demo_returns_the_fixed_problem_without_scraping(client, monkeypatch):
    monkeypatch.setattr(boj_route, "IS_DEMO", True)
    monkeypatch.setattr(api_client, "scrape_boj_problem", lambda pid: pytest.fail("데모가 외부 수집을 했다"))

    body = client.get("/api/problem/boj/1000").json()

    assert body == DEMO_BOJ_PROBLEM
    assert set(body) == {"problem_id", "title", "time_limit", "memory_limit", "statement_sections_html",
                         "statement_sections_ko", "samples", "url"}
