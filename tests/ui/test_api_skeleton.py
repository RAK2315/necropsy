"""Skeleton endpoint: cap, empty body, a real sample."""
from fastapi.testclient import TestClient

from api.index import MAX_UPLOAD, app
from tests.conftest import corpus_bytes

client = TestClient(app)


def test_over_cap_is_413_with_limit():
    r = client.post("/api/analyze", content=b"\x00" * (MAX_UPLOAD + 1))
    assert r.status_code == 413
    assert r.json()["limit_bytes"] == MAX_UPLOAD


def test_exactly_cap_is_accepted():
    r = client.post("/api/analyze", content=b"\x00" * MAX_UPLOAD)
    assert r.status_code == 200


def test_empty_body_is_a_failed_result_not_an_error():
    r = client.post("/api/analyze", content=b"")
    assert r.status_code == 200
    assert r.json()["status"] == "FAILED"


def test_sample_resolves():
    r = client.post("/api/analyze", content=corpus_bytes("mystery_a"))
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "RESOLVED"
    assert body["engine_ms"] >= 0