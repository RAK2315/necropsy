"""Unit tests for the closure gate (row_stride, PCX RLE decoder, check_closure, trailers)."""
from __future__ import annotations

from pathlib import Path

import pytest

from necropsy.engine.closure import (
    check_closure,
    rle_pcx_decode,
    rle_pcx_output_length,
    row_stride,
)
from necropsy.engine.trailers import TRAILER_REGISTRY, TrailerEntry, match_trailer
from necropsy.engine.types import Hypothesis


def corpus_bytes(name: str) -> bytes:
    return (Path(__file__).resolve().parent.parent / "spike" / "samples" / name).read_bytes()


def hyp(**kw):
    base = dict(width=2, height=2, bit_depth=8, header_size=0)
    base.update(kw)
    return Hypothesis(**base)


# ---------------------------------------------------------------- row_stride

@pytest.mark.parametrize(
    "width,bpp,align,expected",
    [
        (4, 1, 1, 1),    # 4 bits -> 1 byte
        (9, 1, 1, 2),    # 9 bits -> 2 bytes
        (16, 24, 1, 48),
        (6, 8, 4, 8),    # 6 bytes rounded up to multiple of 4
        (3, 12, 1, 5),   # 36 bits -> 4.5 -> 5 bytes
    ],
)
def test_row_stride(width, bpp, align, expected):
    assert row_stride(width, bpp, align) == expected


# ------------------------------------------------------------------- decoder

def test_decoder_literal_and_run_mix_ok():
    # 0x01 literal; 0xC3 0x07 = run of 3 x 0x07; 0x02 literal -> 01 07 07 07 02
    data = bytes([0x01, 0xC3, 0x07, 0x02])
    r = rle_pcx_decode(data, 0, len(data), 5)
    assert r.status == "ok"
    assert r.data == bytes([1, 7, 7, 7, 2])
    assert r.consumed_to == len(data)
    assert rle_pcx_output_length(data, 0, len(data)) == 5


def test_decoder_overrun_large_run_small_limit():
    # 0xFF 0xAA = run of 63 x 0xAA, limit 4
    data = bytes([0xFF, 0xAA])
    r = rle_pcx_decode(data, 0, 2, 4)
    assert r.status == "overrun"
    assert r.data is None  # nothing emitted beyond the limit


def test_decoder_trailing_marker_underrun():
    # 0x05 literal, then 0xC2 run marker with no value byte
    data = bytes([0x05, 0xC2])
    r = rle_pcx_decode(data, 0, 2, 3)
    assert r.status == "underrun"
    assert rle_pcx_output_length(data, 0, 2) is None


def test_decoder_unconsumed_leftover():
    # three literals but only 2 bytes wanted: one input byte left over
    data = bytes([1, 2, 3])
    r = rle_pcx_decode(data, 0, 3, 2)
    assert r.status == "unconsumed"
    assert r.consumed_to == 2


def test_decoder_consumed_to_equals_end_on_ok():
    data = bytes([9, 9, 0xC2, 4])  # literals 9 9, run 2 x 4 -> 4 bytes
    r = rle_pcx_decode(data, 1, 4, 3)  # start at 1: 9, run 2x4 -> 3 bytes
    assert r.status == "ok"
    assert r.consumed_to == 4


# ------------------------------------------------------------- check_closure

def test_reason_degenerate_hypothesis():
    assert check_closure(hyp(width=0), b"abcd").reason == "degenerate_hypothesis"


def test_reason_field_out_of_bounds():
    v = check_closure(hyp(data_end=99), b"abcd")
    assert not v.ok and v.reason == "field_out_of_bounds"


def test_reason_arithmetic_mismatch_signed():
    # 2x2 @8bpp needs 4 bytes; 6 present -> +2, 3 present -> -1
    over = check_closure(hyp(), b"abcdef")
    under = check_closure(hyp(), b"abc")
    assert over.reason == "arithmetic_mismatch" and over.discrepancy == 2
    assert under.reason == "arithmetic_mismatch" and under.discrepancy == -1


def test_none_encoding_ok():
    v = check_closure(hyp(), b"abcd")
    assert v.ok and v.decoded == b"abcd" and (v.data_start, v.data_end) == (0, 4)


def test_reason_decoder_overrun():
    v = check_closure(hyp(encoding="rle_pcx"), bytes([0xFF, 0xAA]))  # 63 bytes > 4
    assert v.reason == "decoder_overrun"


def test_reason_decoder_underrun():
    v = check_closure(hyp(encoding="rle_pcx"), bytes([1, 2]))  # only 2 of 4 bytes
    assert v.reason == "decoder_underrun"


def test_reason_decoder_unconsumed():
    v = check_closure(hyp(encoding="rle_pcx"), bytes([1, 2, 3, 4, 5]))  # 1 byte left
    assert v.reason == "decoder_unconsumed"


def test_rle_ok_through_check_closure():
    v = check_closure(hyp(encoding="rle_pcx"), bytes([0xC4, 7]))  # run 4 x 7
    assert v.ok and v.decoded == bytes([7] * 4)


def test_reason_unsupported_encoding():
    assert check_closure(hyp(encoding="lzw"), b"abcd").reason == "unsupported_encoding"


# ------------------------------------------------------------------ trailers

def _palette_file(n_body=10):
    # body bytes, then 0x0C marker, then 768 palette bytes (769-byte trailer)
    return bytes(n_body) + bytes([0x0C]) + bytes(768)


def test_pcx_palette_trailer_applies_to_pcx_and_generic_not_tga():
    data = _palette_file()
    start = len(data) - 769
    assert match_trailer(data, 0, "pcx") == (start, "pcx_palette_256")
    assert match_trailer(data, 0, "generic") == (start, "pcx_palette_256")
    assert match_trailer(data, 0, "tga") == (len(data), None)


def test_extra_registry_entry_changes_match_without_closure_edit():
    data = bytes(10) + bytes([0xAB]) + bytes(3)  # 0xAB marker, 4-byte trailer
    assert match_trailer(data, 0, "tga") == (len(data), None)
    extra = TrailerEntry("test_footer", 4, 0xAB, frozenset({"tga"}))
    reg = TRAILER_REGISTRY + (extra,)
    assert match_trailer(data, 0, "tga", reg) == (10, "test_footer")


# --------------------------------------------------------------- regression

def test_mystery_b_rle_7x7_header128_does_not_close():
    data = corpus_bytes("mystery_b")
    h = Hypothesis(7, 7, 8, 128, 1, "rle_pcx", None, (), "pcx")
    assert not check_closure(h, data).ok


def test_mystery_b_only_area_64_shapes_close():
    data = corpus_bytes("mystery_b")
    closing = set()
    for w in range(1, 257):
        for ht in range(1, 257):
            h = Hypothesis(w, ht, 8, 128, 1, "rle_pcx", None, (), "pcx")
            if check_closure(h, data).ok:
                closing.add((w, ht))
    assert closing == {(1, 64), (2, 32), (4, 16), (8, 8), (16, 4), (32, 2), (64, 1)}
