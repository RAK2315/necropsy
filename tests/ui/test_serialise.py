"""Serialiser, spec zip and endpoints: corpus statuses, lying header, ordering, budgets, never-raises."""
import io
import json
import random
import zipfile

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

import web.serialise as ser
from app import MAX_UPLOAD, app
from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import CORPUS_NAMES, corpus_bytes
from web.serialise import bottom_left_for, palette_for, stage_of, to_payload

client = TestClient(app)

EXPECTED_STATUS = {
    "mystery_a": "RESOLVED", "mystery_b": "RESOLVED", "mystery_c": "RESOLVED",
    "mystery_d": "UNRESOLVED_AMBIGUITY", "mystery_e": "RESOLVED", "mystery_f": "UNRESOLVED_AMBIGUITY",
    "mystery_g": "UNRESOLVED_AMBIGUITY", "mystery_h": "RESOLVED", "mystery_i": "RESOLVED",
}


def payload_for(name_or_bytes):
    data = corpus_bytes(name_or_bytes) if isinstance(name_or_bytes, str) else name_or_bytes
    return to_payload(Engine().run(data), data, 1.0), data


@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_corpus_status_and_json(name):
    p, _ = payload_for(name)
    assert p["status"] == EXPECTED_STATUS[name]
    json.dumps(p)
    assert {"total_checks", "total_file_size", "engine_ms", "rejections", "spec"} <= set(p)


def test_lying_header_payload_has_what_the_screen_needs():
    p, _ = payload_for("mystery_i")
    c = p["candidates"][0]
    assert c["revision_path"] == ["inclusive_bounds", "rle_pcx"]
    assert c["alternative_paths"] == [["rle_pcx", "inclusive_bounds"]]
    enc = [f for f in c["fields"] if f["name"] == "encoding"]
    assert enc and enc[0]["value"] == [0] and enc[0]["offset"] == 2
    assert c["encoding"] == "rle_pcx"
    # the seed rejection, so the screen can show 7 x 7 -> 8 x 8
    seeds = [r for r in p["rejections"] if r["source"] == "pcx"]
    assert seeds and (seeds[0]["hypothesis"]["width"], seeds[0]["hypothesis"]["height"]) == (7, 7)


@pytest.mark.parametrize("name", ["mystery_d", "mystery_f", "mystery_g"])
def test_ambiguous_payload_is_complete_and_in_discovery_order(name):
    data = corpus_bytes(name)
    result = Engine().run(data)
    p = to_payload(result, data, 1.0)
    assert len(p["candidates"]) == len(result.candidates) >= 2
    sig = lambda h: (h.width, h.height, h.bit_depth, h.header_size, h.encoding)
    assert [(c["width"], c["height"], c["bit_depth"], c["header_size"], c["encoding"])
            for c in p["candidates"]] == [sig(c.hypothesis) for c in result.candidates]
    for c in p["candidates"]:
        assert "data_b64" in c["render"] or "failure" in c["render"]
    assert p["reason"] == result.reason


def test_resolved_candidate_pixels_are_present():
    p, _ = payload_for("mystery_c")
    r = p["candidates"][0]["render"]
    assert (r["width"], r["height"], r["channels"]) == (16, 16, "rgb8")


def test_failed_payload_for_non_image():
    p, _ = payload_for(b"hello, this is not an image at all" * 3)
    assert p["status"] in ("FAILED", "UNRESOLVED_AMBIGUITY", "RESOLVED")      # whatever the engine says, it serialises
    json.dumps(p)
    p2, _ = payload_for(b"")
    assert p2["status"] == "FAILED" and p2["termination"] == "input_too_short"
    assert p2["spec"]["error"].startswith("nothing recovered")


def test_stage_of():
    assert [stage_of(s) for s in ("pcx", "tga", "pbm", "tiff", "revision:inclusive_bounds->rle_pcx", "generic", "engine")] \
        == ["probe", "probe", "probe", "probe", "revision", "generic", "engine"]


# ---- palette and orientation helpers ----

def test_palette_for_reads_after_the_marker():
    data = corpus_bytes("mystery_b")
    c = Engine().run(data).candidate
    assert data[c.data_end] == 0x0C
    assert palette_for(c, data) == data[c.data_end + 1:]
    assert len(palette_for(c, data)) == 768
    assert palette_for(c, data[:-1]) is None           # short palette: never padded


def test_palette_absent_without_trailer():
    data = corpus_bytes("mystery_h")
    assert palette_for(Engine().run(data).candidate, data) is None


def test_bottom_left_for():
    from dataclasses import replace
    from necropsy.engine import FieldRecord
    c = Engine().run(corpus_bytes("mystery_c")).candidate
    assert bottom_left_for(c) is False                       # 0x20: top-left
    def with_desc(value):
        fields = tuple(f for f in c.hypothesis.fields if f.name != "image_descriptor") + (
            FieldRecord("image_descriptor", 0x11, "B", value),)
        return replace(c, hypothesis=replace(c.hypothesis, fields=fields))
    assert bottom_left_for(with_desc((0x00,))) is True
    assert bottom_left_for(with_desc((0x20,))) is False
    assert bottom_left_for(with_desc((0x08,))) is True       # alpha-bits set, bit 5 still clear
    assert bottom_left_for(with_desc(("x",))) is False
    assert bottom_left_for(with_desc((0, 0))) is False
    assert bottom_left_for(replace(c, hypothesis=replace(c.hypothesis, fields=()))) is False


# ---- budgets ----

def test_pixel_budget_converts_in_discovery_order_then_stops(monkeypatch):
    monkeypatch.setattr(ser, "PIXEL_BUDGET", 130)
    p, _ = payload_for("mystery_d")
    states = ["data_b64" in c["render"] for c in p["candidates"]]
    first_off = states.index(False)
    assert first_off >= 1 and not any(states[first_off:])
    for c in p["candidates"][first_off:]:
        assert c["render"] == {"failure": ser.NOT_RENDERED}
        assert c["fields"] is not None and c["width"] > 0           # still listed in full


def test_size_budget_keeps_leading_rejections_and_counts_all(monkeypatch):
    data = corpus_bytes("mystery_i")
    result = Engine().run(data)
    total = len(result.rejections)
    assert total >= 3
    monkeypatch.setattr(ser, "SIZE_BUDGET", 19_000)      # the payload without rejections is about 16,200 bytes
    p = to_payload(result, data, 1.0)
    kept = len(p["rejections"])
    assert 0 < kept < total and p["rejections_omitted"] == total - kept
    assert sum(sum(v.values()) for v in p["rejection_counts"].values()) == total
    assert [r["reason"] for r in p["rejections"]] == [r.reason for r in result.rejections][:kept]
    assert [r["source"] for r in p["rejections"]] == [r.source for r in result.rejections][:kept]


def test_large_input_payload_stays_under_four_million():
    data = bytes(random.Random(7).randrange(256) for _ in range(65_536))
    result = Engine().run(data)
    p = to_payload(result, data, 1.0)
    assert len(json.dumps(p, separators=(",", ":"))) <= ser.SIZE_BUDGET
    assert p["rejections_omitted"] + len(p["rejections"]) == len(result.rejections)


# ---- zip ----

@pytest.mark.parametrize("name", ["mystery_e", "mystery_d", "mystery_i"])
def test_zip_has_one_folder_and_exactly_the_emitted_files(name):
    data = corpus_bytes(name)
    r = client.post("/api/spec.zip", content=data)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    spec = emit_spec(Engine().run(data), data)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == sorted(f"{spec.slug}/{n}" for n, _ in spec.files)
    assert len(z.namelist()) == 3
    for n, text in spec.files:
        raw = z.read(f"{spec.slug}/{n}")
        assert raw == text.encode("utf-8") and not raw.startswith(b"\xef\xbb\xbf")


def test_zip_is_404_json_when_nothing_recovered_and_413_over_cap():
    assert client.post("/api/spec.zip", content=b"").status_code == 404
    assert client.post("/api/spec.zip", content=b"\0" * (MAX_UPLOAD + 1)).status_code == 413


# ---- endpoint ----

@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_filename_does_not_change_the_result(name):
    data = corpus_bytes(name)
    a = client.post("/api/analyze", content=data).json()
    b = client.post("/api/analyze", content=data,
                    headers={"Content-Disposition": 'attachment; filename="holiday.jpg"',
                             "X-Filename": "holiday.jpg"}).json()
    a.pop("engine_ms"); b.pop("engine_ms")
    assert a == b


def test_endpoint_returns_full_payload():
    r = client.post("/api/analyze", content=corpus_bytes("mystery_b"))
    p = r.json()
    assert r.status_code == 200 and p["status"] == "RESOLVED" and p["spec"]["slug"] == "pcx"
    assert p["candidates"][0]["render"]["channels"] == "rgb8"


@settings(max_examples=60, deadline=None)
@given(body=st.binary(max_size=MAX_UPLOAD))
def test_endpoint_is_200_and_json_for_arbitrary_bodies(body):
    r = client.post("/api/analyze", content=body)
    assert r.status_code == 200
    assert r.json()["status"] in ("RESOLVED", "UNRESOLVED_AMBIGUITY", "FAILED")


@settings(max_examples=60, deadline=None)
@given(data=st.binary(max_size=3000), seed=st.sampled_from(CORPUS_NAMES), cut=st.integers(0, 1200),
       flip=st.lists(st.tuples(st.integers(0, 1200), st.integers(0, 255)), max_size=6))
def test_to_payload_never_raises_on_arbitrary_and_mutated_inputs(data, seed, cut, flip):
    base = bytearray(corpus_bytes(seed)[: cut or None])
    for i, v in flip:
        if i < len(base):
            base[i] = v
    for blob in (data, bytes(base)):
        p = to_payload(Engine().run(blob), blob, 0.5)
        assert isinstance(p, dict) and p["status"] in ("RESOLVED", "UNRESOLVED_AMBIGUITY", "FAILED")
        json.dumps(p)