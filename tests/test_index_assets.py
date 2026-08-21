"""index.html 자산 캐시 버전 치환 — `?v=` 를 손으로 고치던 방식의 갱신 누락 재발 방지."""
import re

def test_asset_urls_share_one_version(client):
    html = client.get("/").text
    assert "__V__" not in html, "자산 버전 플레이스홀더가 치환되지 않았다"
    versions = set(re.findall(r"\?v=([^\"']+)", html))
    assert len(versions) == 1, f"자산 버전이 갈렸다 — 배포마다 전부 같이 바뀌어야 한다: {versions}"


def test_shell_document_is_revalidated(client):
    # 셸이 캐시되면 새 자산 URL 이 사용자에게 도달하지 못한다.
    assert client.get("/").headers["cache-control"] == "no-cache"


def _local_asset_refs(client) -> list[str]:
    html = client.get("/").text
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert refs, "정적 자산 참조를 찾지 못했다"
    return refs


def test_all_local_asset_references_are_versioned(client):
    # 새 자산을 ?v= 없이 추가해도 위 두 테스트는 통과한다 — 여기서 로컬 참조를 전부 뽑아 확인한다.
    unversioned = [ref for ref in _local_asset_refs(client) if "?v=" not in ref]
    assert not unversioned, f"버전이 없는 로컬 자산 참조: {unversioned}"


def test_every_referenced_asset_is_actually_served(client):
    """참조가 실제로 200 인지 본다 — 버전 검사만으로는 파일이 없어도 통과한다.

    CSS 5개는 index.html 의 로드 순서가 곧 캐스케이드 순서라, 하나를 지우거나 이름을
    바꾸면 페이지가 통째로 무스타일이 된다. 그런데 scripts/check_js.sh 의 고아 파일
    검사에는 CSS 대응물이 없고(JS 만 본다), 이 파일의 나머지 검사는 존재 여부를
    보지 않아 전 게이트가 초록인 채로 배포될 수 있었다.
    """
    missing = []
    for ref in _local_asset_refs(client):
        path = ref.split("?")[0]
        if client.get(path).status_code != 200:
            missing.append(path)
    assert not missing, f"index.html 이 참조하는데 서빙되지 않는 자산: {missing}"
