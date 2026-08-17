"""index.html 자산 캐시 버전 치환 — `?v=` 를 손으로 고치던 방식의 갱신 누락 재발 방지."""
import re

import pytest
from fastapi.testclient import TestClient

import server
import warmup


@pytest.fixture
def client(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(warmup, "warm_theme_caches", _noop)
    with TestClient(server.app) as c:
        yield c


def test_asset_urls_share_one_version(client):
    html = client.get("/").text
    assert "__V__" not in html, "자산 버전 플레이스홀더가 치환되지 않았다"
    versions = set(re.findall(r"\?v=([^\"']+)", html))
    assert len(versions) == 1, f"자산 버전이 갈렸다 — 배포마다 전부 같이 바뀌어야 한다: {versions}"


def test_shell_document_is_revalidated(client):
    # 셸이 캐시되면 새 자산 URL 이 사용자에게 도달하지 못한다.
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_all_local_asset_references_are_versioned(client):
    # 새 자산을 ?v= 없이 추가해도 위 두 테스트는 통과한다 — 여기서 로컬 참조를 전부 뽑아 확인한다.
    html = client.get("/").text
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert refs, "정적 자산 참조를 찾지 못했다"
    unversioned = [ref for ref in refs if "?v=" not in ref]
    assert not unversioned, f"버전이 없는 로컬 자산 참조: {unversioned}"
