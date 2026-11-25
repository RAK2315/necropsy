"""Task 3 (format-coverage): closure rule sample_above_maxval (Requirements 2.16, 2.17, 3.9, 1.5).

Hypothesis objects are built directly; no probe exists for PNM yet.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from necropsy.engine.closure import ClosureVerdict, check_closure
from necropsy.engine.types import REASONS, FailureReport, Hypothesis, RejectionEntry
from web.serialise import to_payload


def hyp(width, height, bit_depth, maxval, header_size=0):
    return Hypothesis(width=width, height=height, bit_depth=bit_depth, header_size=header_size,
                      maxval=maxval, probe_name="pnm")


def test_reason_is_in_vocabulary_req_2_16():
    assert "sample_above_maxval" in REASONS


def test_sample_equal_to_maxval_passes_req_3_9():
    # 2x1 grey, 8 bit, maxval 15: bytes 15 and 0, both within the maximum.
    v = check_closure(hyp(2, 1, 8, 15), bytes([15, 0]))
    assert v.ok and v.decoded == bytes([15, 0])


def test_sample_above_maxval_fails_with_detail_req_3_9():
    # header 3 bytes, then samples 1, 16: the 16 sits at offset 4 and exceeds 15.
    v = check_closure(hyp(2, 1, 8, 15, header_size=3), b"abc" + bytes([1, 16]))
    assert not v.ok and v.reason == "sample_above_maxval"
    assert "4" in v.detail and "16" in v.detail and "15" in v.detail
    assert v.decoded is None


def test_length_rule_runs_first_req_3_9():
    # Wrong length and a bad sample: the length rule reports first.
    v = check_closure(hyp(2, 1, 8, 15), bytes([99, 99, 99]))
    assert v.reason == "arithmetic_mismatch"


def test_16_bit_maxval_1000_checks_both_bytes_req_3_9():
    # 1000 = 0x03E8. 0x03E8 passes; 0x03E9 fails (low byte); 0x0400 fails (high byte).
    assert check_closure(hyp(1, 1, 16, 1000), b"\x03\xe8").ok
    for bad, val in ((b"\x03\xe9", 1001), (b"\x04\x00", 1024)):
        v = check_closure(hyp(1, 1, 16, 1000), bad)
        assert v.reason == "sample_above_maxval" and str(val) in v.detail


def test_16_bit_rgb_samples_req_3_9():
    # 1x1 48-bit pixel: three big-endian samples; the third (offset 4) is 2 > maxval 1.
    v = check_closure(hyp(1, 1, 48, 1), b"\x00\x01\x00\x00\x00\x02")
    assert v.reason == "sample_above_maxval" and "offset 4" in v.detail


def test_maxval_none_and_full_range_unchanged_req_3_9():
    assert check_closure(hyp(1, 1, 8, None), b"\xff").ok
    assert check_closure(hyp(1, 1, 8, 255), b"\xff").ok
    assert check_closure(hyp(1, 1, 16, 65535), b"\xff\xff").ok


def test_serialise_passes_reason_through_req_2_17():
    rej = RejectionEntry("sample_above_maxval", "pcx", None, None, "x")
    result = FailureReport("exhausted", (rej,), 1, 0)
    p = to_payload(result, b"", 0.0)
    assert p["rejections"][0]["reason"] == "sample_above_maxval"
    assert p["rejection_counts"]["probe"]["sample_above_maxval"] == 1


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=64), st.integers(0, 70000), st.sampled_from([8, 16, 24, 48]))
def test_never_raises_req_15_1(data, maxval, depth):
    v = check_closure(hyp(2, 1, depth, maxval), data)
    assert isinstance(v, ClosureVerdict)
    if not v.ok:
        assert v.reason in REASONS
