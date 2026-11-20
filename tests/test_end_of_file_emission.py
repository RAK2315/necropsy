"""End-of-file readings in emission (Requirement 9.27, Decision Record item 24)."""
from __future__ import annotations

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR, corpus_bytes
from tests.support.reference_reader import extract_layout, parse_candidates
from tests.test_trailer_readings import crafted_1036


def _crafted():
    data = crafted_1036(True)
    result = Engine().run(data)
    spec = emit_spec(result, data)
    md = dict(spec.files)["requirements.md"]
    return data, result, md


def test_end_of_file_candidates_emit_no_end_and_no_trailers():
    data, result, md = _crafted()
    layout = build_layout(result, data)
    assert layout["kind"] == "ambiguous" and len(layout["candidates"]) == 3
    for c in layout["candidates"]:
        assert c["data"]["end"] is None
        assert c["data"]["trailers"] == []
        assert c["observed"]["data_end"] == 1036
    assert "THE parser SHALL NOT strip any trailer from the data region." in md


def test_reference_reader_reproduces_each_end_of_file_candidate():
    data, result, md = _crafted()
    outs = parse_candidates(extract_layout(md), data)
    assert len(outs) == 3
    for cand, out in zip(result.candidates, outs):
        assert out.get("ok") is True, out
        assert (out["data_start"], out["data_end"]) == (12, 1036)
        assert (out["width"], out["height"], out["bit_depth"]) == (
            cand.hypothesis.width, cand.hypothesis.height, cand.hypothesis.bit_depth)
        assert out["pixels"] == cand.decoded


def test_candidates_with_a_stripped_trailer_are_unchanged():
    for name in ("mystery_b", "external_b"):
        data = (SAMPLES_DIR / "external" / name).read_bytes() if name.startswith("external") else corpus_bytes(name)
        result = Engine().run(data)
        layout = build_layout(result, data)
        cands = layout["candidates"] if layout["kind"] == "ambiguous" else [layout]
        found = False
        for c in cands:
            if c["observed"]["data_end"] != len(data) and c["data"]["trailers"] is not None \
                    and c["slug"] in ("pcx", "tga"):
                assert c["data"]["trailers"], name
                found = True
        assert found, name