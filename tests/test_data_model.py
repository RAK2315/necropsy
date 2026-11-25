"""Format-coverage Task 2: optional hypothesis fields, key, stride helper (Requirements 7.1 to 7.4, 7.13, 7.14)."""
import json
from dataclasses import replace

import pytest
from hypothesis import given, strategies as st

from necropsy.engine import Engine
from necropsy.engine.closure import ClosureVerdict, check_closure, hypothesis_row_stride, row_stride
from necropsy.engine.types import Candidate, Hypothesis, RejectionEntry, hypothesis_key
from spike.make_samples import build_pcx
from tools import payload_hashes
from web.serialise import _hypothesis

BASE = Hypothesis(width=4, height=3, bit_depth=8, header_size=16)


def test_defaults_and_seven_tuple_key():
    h = BASE
    assert (h.planes, h.row_bytes, h.ranges, h.rows_per_strip, h.tile, h.maxval) == (1, None, (), None, None, None)
    assert hypothesis_key(h) == (4, 3, 8, 16, 1, "none", None)


@pytest.mark.parametrize("change", [
    {"planes": 3}, {"row_bytes": 6}, {"ranges": ((16, 28),)}, {"rows_per_strip": 2},
    {"tile": (16, 16)}, {"maxval": 255},
])
def test_each_new_field_changes_key_with_eighth_element(change):
    k = hypothesis_key(replace(BASE, **change))
    assert k != hypothesis_key(BASE)
    assert len(k) == 8 and k[:7] == hypothesis_key(BASE)


def test_ranges_distinguish_hypotheses():
    a = replace(BASE, ranges=((16, 20),))
    b = replace(BASE, ranges=((16, 24),))
    assert hypothesis_key(a) != hypothesis_key(b)


def test_row_stride_helper():
    assert hypothesis_row_stride(BASE) == row_stride(4, 8, 1)
    assert hypothesis_row_stride(replace(BASE, width=5, bit_depth=1, row_alignment=4)) == 4
    assert hypothesis_row_stride(replace(BASE, row_bytes=210)) == 210


def test_candidate_and_verdict_defaults():
    assert ClosureVerdict(False, "x", None, None, None, None, None).detail == ""
    c = Candidate(BASE, 4, 12, 16, 28, None, None, "not_computed")
    assert c.ranges == ()


def test_hypothesis_dict_adds_keys_only_when_non_default():
    assert set(_hypothesis(BASE)) == {
        "width", "height", "bit_depth", "header_size", "row_alignment", "encoding", "declared_data_end",
        "probe_name", "bounds", "revision_path", "fields"}
    d = _hypothesis(replace(BASE, planes=3, row_bytes=6, ranges=((1, 2),), rows_per_strip=2,
                            tile=(8, 8), maxval=15))
    assert (d["planes"], d["row_bytes"], d["ranges"], d["rows_per_strip"], d["tile"], d["maxval"]) == (
        3, 6, [[1, 2]], 2, [8, 8], 15)


def test_rejection_detail_travels_from_verdict(monkeypatch):
    import necropsy.engine.engine as eng
    real = eng.check_closure

    def with_detail(h, data):
        v = real(h, data)
        return replace(v, detail="why") if not v.ok else v
    monkeypatch.setattr(eng, "check_closure", with_detail)
    # The 8x8 RLE PCX cut after 12 data bytes: the RLE decoder underruns, so the
    # closure gate rejects the pcx reading.
    data = build_pcx()[:140]
    r = Engine().run(data)
    rejs = r.rejections
    assert rejs and any(e.detail == "why" and e.reason == "decoder_underrun" for e in rejs)


def test_payload_of_every_sample_unchanged_byte_for_byte():
    expected = json.loads(open("spike/payload_hashes.json", encoding="utf-8").read())
    assert payload_hashes.measure() == expected


@given(st.binary(max_size=300))
def test_engine_never_raises_and_key_defaults(data):
    r = Engine().run(data)
    assert r.status in {"RESOLVED", "UNRESOLVED_AMBIGUITY", "FAILED"}
    assert isinstance(check_closure(BASE, data).detail, str)
