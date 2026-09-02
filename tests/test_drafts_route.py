"""에디터 임시 저장 API — `/api/drafts/{key}`.

임시 저장은 "코드를 잃지 않는다"가 유일한 존재 이유다. 조용히 실패하면(빈 값을 저장,
없는 저장본을 오류로 보고, 키가 섞임) 기능이 있는 채로 목적을 잃는다.
"""


def test_save_and_get_round_trips_code_and_language(client):
    res = client.post("/api/drafts/main", json={"code": "print(1)", "language": "Python 3"})
    assert res.status_code == 200
    assert res.json()["updated_at"]

    got = client.get("/api/drafts/main").json()
    assert got["code"] == "print(1)"
    # 언어까지 돌려줘야 복원 시 에디터 모드가 따라온다 — 코드만 복원하면 C++ 이 파이썬 모드로 열린다.
    assert got["language"] == "Python 3"
    assert got["updated_at"]


def test_saving_again_overwrites_the_same_key(client):
    client.post("/api/drafts/main", json={"code": "a = 1", "language": "Python 3"})
    client.post("/api/drafts/main", json={"code": "a = 2", "language": "Python 3"})
    assert client.get("/api/drafts/main").json()["code"] == "a = 2"


def test_missing_draft_is_an_empty_payload_not_an_error(client):
    """404 로 주면 프론트가 '아직 없음' 과 '조회 실패' 를 구분하지 못한다."""
    res = client.get("/api/drafts/codeforces:4A")
    assert res.status_code == 200
    assert res.json() == {"key": "codeforces:4A", "code": "", "language": "", "updated_at": None}


def test_blank_code_deletes_the_draft(client):
    client.post("/api/drafts/codeforces:4A", json={"code": "x = 1", "language": "Python 3"})
    res = client.post("/api/drafts/codeforces:4A", json={"code": "   \n", "language": "Python 3"})
    # 지웠다는 신호가 updated_at=None 이다.
    assert res.json()["updated_at"] is None
    assert client.get("/api/drafts/codeforces:4A").json()["code"] == ""


def test_keys_are_independent(client):
    """문제마다 자리가 다르다 — 한 문제에 쓴 코드가 다른 문제에 나타나면 안 된다."""
    client.post("/api/drafts/codeforces:4A", json={"code": "aaa", "language": ""})
    client.post("/api/drafts/codeforces:1352G", json={"code": "bbb", "language": ""})
    client.post("/api/drafts/main", json={"code": "ccc", "language": ""})
    assert client.get("/api/drafts/codeforces:4A").json()["code"] == "aaa"
    assert client.get("/api/drafts/codeforces:1352G").json()["code"] == "bbb"
    assert client.get("/api/drafts/main").json()["code"] == "ccc"


def test_malformed_key_is_rejected(client):
    """키는 그대로 PK 가 된다 — 임의 문자열을 받으면 표가 쓰레기로 찬다."""
    for bad in ("문제", "a" * 81, "main!"):
        assert client.get(f"/api/drafts/{bad}").status_code == 400
        assert client.post(f"/api/drafts/{bad}", json={"code": "x"}).status_code == 400


def test_oversized_code_is_rejected(client):
    """리뷰 제출과 같은 상한을 쓴다 — 임시 저장만 무제한이면 상한이 무의미하다."""
    from routes.models import MAX_CODE_LENGTH
    res = client.post("/api/drafts/main", json={"code": "x" * (MAX_CODE_LENGTH + 1)})
    assert res.status_code == 422
    # 거부된 요청이 기존 저장본을 건드리지 않는다.
    assert client.get("/api/drafts/main").json()["code"] == ""
