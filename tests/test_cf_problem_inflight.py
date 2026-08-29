"""/api/problem/cf 의 같은 문제 동시 요청 병합.

캐시는 결과가 들어간 뒤에만 듣는다. 조회부터 저장까지는 스크래핑 1회 + 유료 번역 4건이라
수 초~십수 초 걸리고, 그 사이 들어온 같은 문제 요청은 전부 캐시 미스가 되어 각자 번역을 돌린다.
in-flight 맵이 그 구간을 한 작업으로 묶는다.
"""
import asyncio
import threading

import httpx
import pytest
import requests
from fastapi import FastAPI

import clients as api_client
from routes import problem as problem_route

_RAW = {
    "title": "Watermelon",
    "statement": "본문", "input": "입력 설명", "output": "출력 설명", "note": "노트",
    "time_limit": "1 second", "memory_limit": "256 megabytes",
    "samples": [], "url": "https://codeforces.com/problemset/problem/4/A",
    "contest_id": 4, "index": "A",
}
_URL = "/api/problem/cf/4A"


@pytest.fixture(autouse=True)
def clean_route_state():
    """캐시와 in-flight 맵은 모듈 전역이라 테스트 사이에 남는다."""
    problem_route._PROBLEM_CACHE.clear()
    problem_route._IN_FLIGHT.clear()
    yield
    problem_route._PROBLEM_CACHE.clear()
    problem_route._IN_FLIGHT.clear()


@pytest.fixture
def stubs(monkeypatch):
    """스크래핑·번역 호출을 세는 대역.

    scrape 는 gate 가 열릴 때까지 스레드에서 멈춘다 — 그 사이에 두 번째 요청을 넣어
    "캐시에 아직 없는 구간" 을 재현한다. 번역은 스레드에서 호출되므로 원자적인
    list.append 로 센다.
    """
    calls = {"scrape": [], "translate": [], "gate": threading.Event()}

    def _scrape(ref):
        calls["scrape"].append(ref)
        calls["gate"].wait(5)
        return dict(_RAW)

    def _translate(text, title):
        calls["translate"].append(text)
        return "[ko]" + text

    monkeypatch.setattr(api_client, "scrape_cf_problem", _scrape)
    monkeypatch.setattr(problem_route, "translate_cf_text", _translate)
    return calls


def _client():
    app = FastAPI()
    app.include_router(problem_route.router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def test_concurrent_requests_scrape_and_translate_once(stubs):
    """동시 2건이 유료 번역을 두 벌 돌리면 안 된다."""
    async def _main():
        async with _client() as client:
            pending = [asyncio.ensure_future(client.get(_URL)) for _ in range(2)]
            await asyncio.sleep(0.2)   # 두 요청 모두 라우터에 진입할 시간
            stubs["gate"].set()
            return await asyncio.gather(*pending)

    first, second = asyncio.run(_main())

    assert [first.status_code, second.status_code] == [200, 200]
    assert len(stubs["translate"]) == 4     # 유료 호출 — 동시 요청 수와 무관해야 한다
    assert len(stubs["scrape"]) == 1
    assert first.json() == second.json()
    assert first.json()["statement_sections_ko"]["statement"] == "[ko]본문"


def test_sequential_requests_still_hit_the_cache(stubs):
    """순차 경로는 그대로 캐시가 받는다."""
    stubs["gate"].set()

    async def _main():
        async with _client() as client:
            return await client.get(_URL), await client.get(_URL)

    first, second = asyncio.run(_main())

    assert [first.status_code, second.status_code] == [200, 200]
    assert len(stubs["scrape"]) == 1
    assert len(stubs["translate"]) == 4


def test_waiter_survives_the_initiator_cancellation(stubs):
    """개시 요청이 끊겨도 대기 중인 요청은 정상 응답을 받아야 한다."""
    async def _main():
        async with _client() as client:
            initiator = asyncio.ensure_future(client.get(_URL))
            await asyncio.sleep(0.2)   # 개시자가 작업을 등록할 시간
            waiter = asyncio.ensure_future(client.get(_URL))
            await asyncio.sleep(0.1)   # 대기자가 그 작업에 붙을 시간
            initiator.cancel()
            stubs["gate"].set()
            resp = await waiter
            await asyncio.gather(initiator, return_exceptions=True)
            return resp

    resp = asyncio.run(_main())

    assert resp.status_code == 200
    assert len(stubs["scrape"]) == 1
    assert len(stubs["translate"]) == 4


def test_failed_fetch_does_not_stick(monkeypatch):
    """실패한 작업이 맵에 남으면 그 문제가 영구 실패로 굳는다."""
    attempts = []

    def _scrape(ref):
        attempts.append(ref)
        if len(attempts) == 1:
            raise requests.HTTPError("boom")
        return dict(_RAW)

    monkeypatch.setattr(api_client, "scrape_cf_problem", _scrape)
    monkeypatch.setattr(problem_route, "translate_cf_text", lambda text, title: text)

    async def _main():
        async with _client() as client:
            return await client.get(_URL), await client.get(_URL)

    first, second = asyncio.run(_main())

    assert first.status_code == 502
    assert second.status_code == 200
    assert len(attempts) == 2
    assert problem_route._IN_FLIGHT == {}


def test_concurrent_waiters_share_the_failure(stubs, monkeypatch):
    """실패도 대기자에게 그대로 전달된다 — 404 는 404 로 남아야 한다."""
    response = requests.Response()
    response.status_code = 404

    def _scrape(ref):
        stubs["scrape"].append(ref)
        stubs["gate"].wait(5)
        raise requests.HTTPError("not found", response=response)

    monkeypatch.setattr(api_client, "scrape_cf_problem", _scrape)

    async def _main():
        async with _client() as client:
            pending = [asyncio.ensure_future(client.get(_URL)) for _ in range(2)]
            await asyncio.sleep(0.2)
            stubs["gate"].set()
            return await asyncio.gather(*pending)

    first, second = asyncio.run(_main())

    assert [first.status_code, second.status_code] == [404, 404]
    assert len(stubs["scrape"]) == 1
    assert len(stubs["translate"]) == 0


def test_malformed_ref_is_rejected_before_any_scraping(stubs):
    """400 분기는 in-flight 맵에 아무것도 남기지 않는다."""
    async def _main():
        async with _client() as client:
            return await client.get("/api/problem/cf/nope")

    resp = asyncio.run(_main())

    assert resp.status_code == 400
    assert stubs["scrape"] == []
    assert problem_route._IN_FLIGHT == {}
