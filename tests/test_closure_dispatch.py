"""Task 7 (format-coverage): decoder dispatch and the decode cap (Requirements 2.12, 2.13, 2.16, 2.17, 4.12, 15.1)."""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

import necropsy.engine.decoders as decoders
from necropsy.engine.closure import ClosureVerdict, check_closure
from necropsy.engine.decoders import DECODE_CAP, DECODERS, STATUS_REASONS, DecodeResult
from necropsy.engine.types import REASONS, FailureReport, Hypothesis, RejectionEntry
from web.serialise import to_payload


def hyp(width, height, bit_depth=8, maxval=255, encoding="pnm_text", header_size=0):
    return Hypothesis(width=width, height=height, bit_depth=bit_depth, header_size=header_size,
                      maxval=maxval, encoding=encoding, probe_name="pnm")


def test_both_new_reasons_in_vocabulary_req_2_16():
    assert {"sample_above_maxval", "decoder_malformed"} <= REASONS
    assert len(REASONS) == 12


def test_pnm_text_is_first_entry_req_4_12():
    assert list(DECODERS)[0] == "pnm_text"


def test_pnm_text_ok_through_gate_req_4_12():
    v = check_closure(hyp(2, 1), b"1 2\n")
    assert v.ok and v.decoded == bytes([1, 2]) and v.data_end == 4


@pytest.mark.parametrize("data,reason", [
    (b"1", "decoder_underrun"),          # one number short
    (b"1 2 3", "decoder_unconsumed"),    # one number too many
    (b"1 x", "decoder_malformed"),       # non-digit token
    (b"1 300", "sample_above_maxval"),   # above maxval 255
])
def test_real_decoder_states_map_to_reasons_req_2_12(data, reason):
    v = check_closure(hyp(2, 1), data)
    assert not v.ok and v.reason == reason and v.detail
    assert v.decoded is None


@pytest.mark.parametrize("status,reason", sorted(STATUS_REASONS.items()))
def test_every_state_maps_and_carries_detail_req_2_12(monkeypatch, status, reason):
    monkeypatch.setitem(DECODERS, "fake",
                        lambda data, s, e, h, n: DecodeResult(status, None, s, "why " + status))
    v = check_closure(hyp(2, 1, encoding="fake"), b"xx")
    assert not v.ok and v.reason == reason and v.detail == "why " + status


def test_status_map_reasons_are_in_vocabulary():
    assert set(STATUS_REASONS) == set(decoders.STATUSES) - {"ok"}
    assert set(STATUS_REASONS.values()) <= REASONS


def test_cap_boundary_req_2_13():
    at = check_closure(hyp(DECODE_CAP, 1), b"1")
    assert at.reason != "degenerate_hypothesis"  # exactly the cap reaches the decoder
    over = check_closure(hyp(DECODE_CAP + 1, 1), b"1")
    assert over.reason == "degenerate_hypothesis"
    assert str(DECODE_CAP + 1) in over.detail and str(DECODE_CAP) in over.detail


def test_none_encoding_is_not_capped_req_2_13():
    v = check_closure(hyp(DECODE_CAP + 1, 1, encoding="none", maxval=None), b"x")
    assert v.reason == "arithmetic_mismatch"


@pytest.mark.parametrize("enc", ["tiff_compression_5", "x"])
def test_unknown_encoding_still_unsupported_req_2_13(enc):
    assert check_closure(hyp(2, 2, encoding=enc), bytes(4)).reason == "unsupported_encoding"


def test_new_reasons_pass_through_serialise_req_2_17():
    rejs = tuple(RejectionEntry(r, "pcx", None, None, "x")
                 for r in ("sample_above_maxval", "decoder_malformed"))
    p = to_payload(FailureReport("exhausted", rejs, 2, 0), b"", 0.0)
    assert [r["reason"] for r in p["rejections"]] == ["sample_above_maxval", "decoder_malformed"]
    counts = p["rejection_counts"]["probe"]
    assert counts["sample_above_maxval"] == 1 and counts["decoder_malformed"] == 1


@settings(max_examples=100, deadline=None)
@given(data=st.binary(max_size=256), w=st.integers(-3, 20), h=st.integers(-3, 20),
       depth=st.sampled_from([1, 8, 16, 24, 48]), maxval=st.one_of(st.none(), st.integers(-1, 70000)))
def test_dispatch_never_raises_req_15_1(data, w, h, depth, maxval):
    v = check_closure(hyp(w, h, depth, maxval), data)
    assert isinstance(v, ClosureVerdict)
    if not v.ok:
        assert v.reason in REASONS and v.decoded is None
