"""Unit tests for the closure gate (task 2.4).

Every expected value comes from requirements.md (Req 1.x, Decision Record
item 4) or design.md ("Trailer Registry", "Closure"). Each test cites the
criterion and shows the arithmetic. Inputs are built in code from documented
layouts.
"""
from __future__ import annotations

import pytest

from necropsy.engine.closure import (
    RleResult,
    check_closure,
    rle_pcx_decode,
    rle_pcx_output_length,
    row_stride,
)
from necropsy.engine.trailers import TRAILER_REGISTRY, TrailerEntry, match_trailer
from necropsy.engine.types import Hypothesis
from tests.conftest import corpus_bytes


def hyp(width, height, bit_depth=8, header_size=0, row_alignment=1,
        encoding="none", data_end=None, probe_name="generic"):
    return Hypothesis(
        width=width, height=height, bit_depth=bit_depth, header_size=header_size,
        row_alignment=row_alignment, encoding=encoding, data_end=data_end,
        probe_name=probe_name,
    )


# --------------------------------------------------------------- row_stride
# Req 1.1: row_stride = round_up(ceil(width * bit_depth / 8), row_alignment)
@pytest.mark.parametrize(
    "width, bpp, align, expected",
    [
        (4, 1, 1, 1),    # ceil(4*1/8)=ceil(0.5)=1; round_up(1,1)=1
        (9, 1, 1, 2),    # ceil(9/8)=2; round_up(2,1)=2
        (16, 24, 1, 48),  # ceil(16*24/8)=48; round_up(48,1)=48
        (6, 8, 4, 8),    # ceil(6*8/8)=6; round_up(6,4)=8
        (3, 12, 1, 5),   # ceil(3*12/8)=ceil(4.5)=5; round_up(5,1)=5
    ],
)
def test_row_stride_req_1_1(width, bpp, align, expected):
    assert row_stride(width, bpp, align) == expected


# ------------------------------------------------------------------ decoder
def test_decoder_ok_literal_and_run_mix_req_1_9_1_11():
    # Req 1.9: b >= 0xC0 is a run of (b & 0x3F) copies of the next byte; else literal.
    # 0x41 literal; 0xC3 0x07 run of 3 x 0x07; 0x42 literal -> 1+3+1 = 5 bytes.
    data = b"\x41" + b"\xC3\x07" + b"\x42"
    r = rle_pcx_decode(data, 0, len(data), 5)
    assert isinstance(r, RleResult)
    assert r.status == "ok"
    assert r.data == b"\x41\x07\x07\x07\x42"
    assert r.consumed_to == len(data)  # Req 1.11: ok means stopped exactly at end (4)


def test_decoder_ok_respects_start_and_end_req_1_11():
    # 2 junk bytes, then region [2, 4) = 0x41 0x42, then 1 junk byte beyond end.
    data = b"\xEE\xEE" + b"\x41\x42" + b"\xEE"
    r = rle_pcx_decode(data, 2, 4, 2)
    assert r.status == "ok" and r.data == b"\x41\x42"
    assert r.consumed_to == 4  # equals end


def test_decoder_overrun_req_1_10():
    # 0xFF = run of 0x3F = 63 copies of 0x09, against max_output_bytes = 4.
    r = rle_pcx_decode(b"\xFF\x09", 0, 2, 4)
    assert r.status == "overrun"
    assert r.data is None  # nothing beyond the limit is returned


def test_decoder_overrun_after_partial_output_req_1_10():
    # literal 0x01 (1 byte out), then run 0xC5 = 5 copies; 1+5=6 > max 4 -> overrun.
    r = rle_pcx_decode(b"\x01\xC5\x09", 0, 3, 4)
    assert r.status == "overrun" and r.data is None


def test_decoder_underrun_marker_is_last_byte_req_1_11():
    # 0x41 literal (1 out); 0xC2 is a run marker with no value byte left. max 3.
    r = rle_pcx_decode(b"\x41\xC2", 0, 2, 3)
    assert r.status == "underrun"
    assert r.data is None


def test_decoder_underrun_region_ends_early_req_1_11():
    # two literals -> 2 bytes out, but max_output_bytes = 5.
    r = rle_pcx_decode(b"\x41\x42", 0, 2, 5)
    assert r.status == "underrun" and r.data is None


def test_decoder_unconsumed_req_1_11():
    # three literals, max_output_bytes = 2: output completes after 2, 1 byte remains.
    r = rle_pcx_decode(b"\x41\x42\x43", 0, 3, 2)
    assert r.status == "unconsumed" and r.data is None


@pytest.mark.parametrize(
    "data, start, end, max_out, status, consumed_to",
    [
        # ok, stopped exactly at end (Req 1.11: ok -> data_end). Bytes at [1, 4):
        # 1: 0x41 literal; 2: 0xC2 run marker; 3: 0x07 value (2 x 0x07). Out = 3.
        # Byte 4 (0xEE) is beyond end and untouched. consumed_to = end = 4.
        (b"\xEE\x41\xC2\x07\xEE", 1, 4, 3, "ok", 4),
        # overrun, value byte followed by leftovers. Bytes: 0: 0xC5 marker (5 copies);
        # 1: 0x09 value; 2: 0x07 leftover. max 4 < 5. Index after value byte = 1 + 1 = 2
        # (not data_end 3).
        (b"\xC5\x09\x07", 0, 3, 4, "overrun", 2),
        # overrun after partial output, with start offset. 0: 0xEE junk; 1: 0x01 literal;
        # 2: 0xC5 marker; 3: 0x09 value. 1 + 5 = 6 > 4. After value byte = 3 + 1 = 4.
        (b"\xEE\x01\xC5\x09", 1, 4, 4, "overrun", 4),
        # underrun, marker last. 0: 0x41 literal; 1: 0xC2 marker, no value byte;
        # 2: 0xEE beyond end. consumed_to = end = 2.
        (b"\x41\xC2\xEE", 0, 2, 3, "underrun", 2),
        # underrun, region ended early. 0: 0x41; 1: 0x42 (2 bytes out, max 5);
        # 2: 0xEE beyond end. consumed_to = end = 2.
        (b"\x41\x42\xEE", 0, 2, 5, "underrun", 2),
        # unconsumed, start offset. 0: 0xEE junk; 1: 0x41; 2: 0x42 (output full at max 2);
        # 3: 0x43 first leftover; 4: 0x44 leftover. First leftover index = 1 + 2 = 3.
        (b"\xEE\x41\x42\x43\x44", 1, 5, 2, "unconsumed", 3),
        # out-of-range: start < 0 -> start = -1.
        (b"\x01", -1, 1, 1, "underrun", -1),
        # out-of-range: end 5 > len 1 -> start = 0.
        (b"\x01", 0, 5, 1, "underrun", 0),
        # out-of-range: start 2 > end 1 -> start = 2.
        (b"\x01\x02", 2, 1, 1, "underrun", 2),
        # negative max_output_bytes -> start = 1.
        (b"\x01\x02", 1, 2, -1, "underrun", 1),
    ],
)
def test_decoder_consumed_to_per_status_req_1_11(data, start, end, max_out, status, consumed_to):
    r = rle_pcx_decode(data, start, end, max_out)
    assert r.status == status
    assert r.consumed_to == consumed_to


def test_decoder_bad_range_is_underrun_not_raise():
    # design.md "Closure": start < 0, end > len(data), start > end, max < 0 -> underrun.
    assert rle_pcx_decode(b"\x01", -1, 1, 1).status == "underrun"
    assert rle_pcx_decode(b"\x01", 0, 5, 1).status == "underrun"
    assert rle_pcx_decode(b"\x01\x02", 2, 1, 1).status == "underrun"
    assert rle_pcx_decode(b"\x01", 0, 1, -1).status == "underrun"


def test_rle_output_length_counts_without_allocating():
    # design.md: literal=1, run=(b & 0x3F). 0x41 (1) + 0xC3 0x07 (3) + 0x42 (1) = 5.
    data = b"\x41\xC3\x07\x42"
    assert rle_pcx_output_length(data, 0, 4) == 5
    # design.md: marker as last byte -> None.
    assert rle_pcx_output_length(b"\x41\xC2", 0, 2) is None


# ------------------------------------------------------------ check_closure
def test_closure_ok_none_encoding_req_1_7():
    # 3x2 at 8 bpp: stride = ceil(24/8)=3, expected = 3*2 = 6. Header 2, region 6 bytes.
    data = b"\xAA\xBB" + bytes(range(1, 7))
    v = check_closure(hyp(3, 2, header_size=2), data)
    assert v.ok is True
    assert v.decoded == bytes(range(1, 7))
    assert (v.data_start, v.data_end, v.trailer) == (2, 8, None)


def test_closure_degenerate_hypothesis_req_1_2():
    data = bytes(16)
    bad = [
        hyp(0, 2),                      # width <= 0
        hyp(2, 0),                      # height <= 0
        hyp(2, 2, bit_depth=0),         # bit_depth <= 0
        hyp(2, 2, row_alignment=3),     # alignment not in {1,2,4}
        hyp(2, 2, header_size=-1),      # header_size < 0
        hyp(2, 2, header_size=17),      # header_size > len(data) = 16
    ]
    for h in bad:
        v = check_closure(h, data)
        assert v.ok is False and v.reason == "degenerate_hypothesis", h


def test_closure_field_out_of_bounds_req_1_4():
    data = bytes(10)
    # declared data_end 11 > len(data) 10
    assert check_closure(hyp(2, 2, data_end=11), data).reason == "field_out_of_bounds"
    # declared data_end 3 < header_size 4
    assert check_closure(hyp(2, 2, header_size=4, data_end=3), data).reason == "field_out_of_bounds"


def test_closure_declared_data_end_is_used_req_1_3():
    # header 2, declared data_end 6 -> region 4 = 2x2 at 8bpp (stride 2, expected 4).
    data = bytes(10)
    v = check_closure(hyp(2, 2, header_size=2, data_end=6), data)
    assert v.ok and v.data_end == 6 and v.trailer is None


def test_closure_arithmetic_mismatch_negative_discrepancy_req_1_7():
    # 3x3 at 8 bpp: expected 9. data 10 bytes, header 2 -> region 8.
    # discrepancy = (data_end - header_size) - expected = 8 - 9 = -1.
    v = check_closure(hyp(3, 3, header_size=2), bytes(10))
    assert v.ok is False
    assert v.reason == "arithmetic_mismatch"
    assert v.discrepancy == -1


def test_closure_arithmetic_mismatch_positive_discrepancy_req_1_7():
    # 3x3 at 8 bpp: expected 9. header 0, region 12. discrepancy = 12 - 9 = +3.
    v = check_closure(hyp(3, 3), bytes(12))
    assert v.reason == "arithmetic_mismatch" and v.discrepancy == 3


def test_closure_decoder_overrun_req_1_12():
    # 2x2 at 8 bpp: expected 4. Region 0xFF 0x09 = run of 63 > 4 -> overrun.
    v = check_closure(hyp(2, 2, encoding="rle_pcx"), b"\xFF\x09")
    assert v.ok is False and v.reason == "decoder_overrun"


def test_closure_decoder_underrun_req_1_12():
    # expected 4. 0x41 literal, then marker 0xC2 as last byte -> underrun.
    v = check_closure(hyp(2, 2, encoding="rle_pcx"), b"\x41\xC2")
    assert v.ok is False and v.reason == "decoder_underrun"


def test_closure_decoder_unconsumed_req_1_12():
    # expected 4. Five literals: output is full after 4, 1 byte remains.
    v = check_closure(hyp(2, 2, encoding="rle_pcx"), b"\x01\x02\x03\x04\x05")
    assert v.ok is False and v.reason == "decoder_unconsumed"


def test_closure_rle_ok_req_1_8():
    # expected 4: 0xC2 0x07 (2 x 0x07) + 0x01 + 0x02 = 4 bytes, region fully consumed.
    v = check_closure(hyp(2, 2, encoding="rle_pcx"), b"\xC2\x07\x01\x02")
    assert v.ok is True and v.decoded == b"\x07\x07\x01\x02"


# rle_tga row removed by format-coverage task 11 (Requirement 5.9); task 12 owns the rest.
@pytest.mark.parametrize("enc", ["tiff_compression_5", "x"])
def test_closure_unsupported_encoding_req_1_13(enc):
    # 2x2 at 8 bpp over 4 bytes would close under "none"; the encoding alone rejects it.
    v = check_closure(hyp(2, 2, encoding=enc), bytes(4))
    assert v.ok is False and v.reason == "unsupported_encoding"


# ----------------------------------------------------------------- trailers
def _trailer_file():
    # 4 header bytes + 10 body bytes + 769-byte trailer whose first byte is 0x0C.
    # len = 4 + 10 + 769 = 783; trailer_start = 783 - 769 = 14; data[14] = 0x0C.
    return bytes(4) + bytes(range(10)) + b"\x0C" + bytes(768)


def test_registry_first_entry_req_1_5():
    e = TRAILER_REGISTRY[0]
    assert (e.name, e.length, e.signature, e.signature_offset) == (
        "pcx_palette_256", 769, b"\x0c", 0)
    assert set(e.applies_to) == {"pcx", "generic"}


def test_registry_second_entry_and_order_req_1_5():
    # Requirement 1.5: pcx_palette_256 first, tga2_footer second, nothing else.
    assert [e.name for e in TRAILER_REGISTRY] == ["pcx_palette_256", "tga2_footer"]
    e = TRAILER_REGISTRY[1]
    assert (e.name, e.length, e.signature, e.signature_offset) == (
        "tga2_footer", 26, b"TRUEVISION-XFILE.\x00", 8)
    assert len(e.signature) == 18
    assert set(e.applies_to) == {"tga", "generic"}


def _footer_file():
    # 4 header bytes + 10 body bytes + 26-byte footer.
    # Footer: 4-byte extension offset (0), 4-byte developer offset (0), then the
    # 18-byte signature "TRUEVISION-XFILE.\0". len = 4 + 10 + 26 = 40;
    # trailer_start = 40 - 26 = 14; signature starts at 14 + 8 = 22 = len - 18.
    return bytes(4) + bytes(range(10)) + bytes(8) + b"TRUEVISION-XFILE.\x00"


@pytest.mark.parametrize("origin", ["tga", "generic"])
def test_tga2_footer_applies_to_tga_and_generic_req_1_5(origin):
    data = _footer_file()
    assert len(data) == 40
    assert match_trailer(data, 4, origin) == (14, "tga2_footer")


@pytest.mark.parametrize("origin", ["pcx", "pbm", "tiff"])
def test_tga2_footer_not_applied_to_other_origins_req_1_5(origin):
    data = _footer_file()
    assert match_trailer(data, 4, origin) == (len(data), None)


@pytest.mark.parametrize("index", [0, 8, 17])
def test_tga2_footer_one_byte_signature_change_stops_match_req_1_5(index):
    data = _footer_file()
    pos = len(data) - 18 + index  # a byte inside the 18-byte signature
    bad = data[:pos] + bytes((data[pos] ^ 0x01,)) + data[pos + 1:]
    assert match_trailer(bad, 4, "tga") == (len(bad), None)


@pytest.mark.parametrize("origin", ["pcx", "generic"])
def test_trailer_applies_to_pcx_and_generic_req_1_5(origin):
    data = _trailer_file()
    assert match_trailer(data, 4, origin) == (14, "pcx_palette_256")


@pytest.mark.parametrize("origin", ["tga", "pbm", "tiff"])
def test_trailer_not_applied_to_other_origins_req_1_5(origin):
    data = _trailer_file()
    assert match_trailer(data, 4, origin) == (len(data), None)


def test_trailer_requires_marker_and_room_for_header_req_1_5():
    data = _trailer_file()
    # marker byte at 14 changed -> no match
    bad = data[:14] + b"\x0D" + data[15:]
    assert match_trailer(bad, 4, "pcx") == (len(bad), None)
    # len - length = 14: header_size 14 satisfies >= ; header_size 15 does not.
    assert match_trailer(data, 14, "pcx") == (14, "pcx_palette_256")
    assert match_trailer(data, 15, "pcx") == (len(data), None)


def test_check_closure_uses_trailer_for_pcx_not_tga_req_1_3():
    data = _trailer_file()
    # 2x5 at 8 bpp: expected 10; header 4; PCX region [4, 14) = 10 -> closes.
    v = check_closure(hyp(2, 5, header_size=4, probe_name="pcx"), data)
    assert v.ok and v.trailer == "pcx_palette_256" and v.data_end == 14
    # TGA origin: no trailer, region [4, 783) = 779; discrepancy = 779 - 10 = 769.
    v = check_closure(hyp(2, 5, header_size=4, probe_name="tga"), data)
    assert v.reason == "arithmetic_mismatch" and v.discrepancy == 769


def test_extra_registry_entry_changes_match_req_1_6():
    # 10 body bytes + 4-byte footer: 0xEE marker at len - 4 = 10.
    data = bytes(10) + b"\xEE\x00\x00\x00"
    footer = TrailerEntry("test_footer", 4, b"\xEE", 0, frozenset({"tga"}))
    registry = TRAILER_REGISTRY + (footer,)
    assert match_trailer(data, 0, "tga") == (14, None)  # default registry: no match
    assert match_trailer(data, 0, "tga", registry) == (10, "test_footer")
    assert match_trailer(data, 0, "pcx", registry) == (14, None)  # scope: tga only


# -------------------------------------------------- mystery_b regression
# Req 1.11 and Decision Record item 4: closure consumes the whole data region.
# Req 7.2: mystery_b is PCX RLE, 8x8, header 128, region [128, 186), pcx_palette_256.
def test_mystery_b_true_reading_closes_req_7_2():
    data = corpus_bytes("mystery_b")
    v = check_closure(hyp(8, 8, header_size=128, encoding="rle_pcx", probe_name="pcx"), data)
    assert v.ok
    assert (v.data_start, v.data_end, v.trailer) == (128, 186, "pcx_palette_256")
    assert len(v.decoded) == 64  # 8 * 8 at 8 bpp


def test_mystery_b_7x7_rle_does_not_close_decision_4():
    data = corpus_bytes("mystery_b")
    v = check_closure(hyp(7, 7, header_size=128, encoding="rle_pcx", probe_name="pcx"), data)
    assert v.ok is False
    # Req 7.2 / tasks.md 2.4: the stream decodes 49 bytes before the region ends.
    assert v.reason == "decoder_unconsumed"


def test_mystery_b_only_area_64_shapes_close_decision_4():
    data = corpus_bytes("mystery_b")
    # Fixed per tasks.md 2.4: encoding "rle_pcx" and origin "pcx" (probe_name="pcx"),
    # because the PCX palette trailer then applies and the RLE region [128, 186)
    # decodes to 64 bytes. Under encoding "none" the region is 58 bytes, so the
    # closing shapes would have area 58, not 64.
    closing = set()
    for w in range(1, 257):
        for h in range(1, 257):
            v = check_closure(
                hyp(w, h, header_size=128, encoding="rle_pcx", probe_name="pcx"), data
            )
            if v.ok:
                closing.add((w, h))
    # Region [128, 186) decodes to 64 bytes; at 8 bpp, align 1, stride = w and
    # expected = w*h, so only w*h = 64 can close: divisors of 64.
    assert closing == {(1, 64), (2, 32), (4, 16), (8, 8), (16, 4), (32, 2), (64, 1)}


# ------------------------------------------------------- property tests (2.5)
from hypothesis import given, settings, strategies as st  # noqa: E402

from necropsy.engine.closure import ClosureVerdict  # noqa: E402
from necropsy.engine.types import REASONS  # noqa: E402

RLE_STATUSES = {"ok", "overrun", "underrun", "unconsumed"}


@st.composite
def valid_rle_streams(draw):
    """(stream, known_output_length). Run: 0xC0|n (n in 1..63) + value byte
    (n bytes out, Req 1.9); literal: byte < 0xC0 (1 byte out)."""
    items = draw(st.lists(
        st.one_of(
            st.tuples(st.integers(1, 63), st.integers(0, 255)).map(
                lambda t: (bytes((0xC0 | t[0], t[1])), t[0])),
            st.integers(0, 0xBF).map(lambda b: (bytes((b,)), 1)),
        ),
        max_size=200,
    ))
    return b"".join(s for s, _ in items), sum(n for _, n in items)


# Feature: structure-inference-engine, Property 6: RLE decoder is bounded and typed
# **Validates: Requirements 1.9, 1.10, 1.11, 6.4**
@settings(max_examples=100, deadline=None)
@given(
    data=st.binary(max_size=65536),
    start=st.integers(),
    end=st.integers(),
    max_out=st.integers(-10, 10**9),
)
def test_property_6_rle_decoder_bounded_and_typed_arbitrary(data, start, end, max_out):
    r = rle_pcx_decode(data, start, end, max_out)
    assert isinstance(r, RleResult)
    assert r.status in RLE_STATUSES
    if r.status == "ok":
        assert len(r.data) == max_out
        assert r.consumed_to == end
    else:
        assert r.data is None


# Feature: structure-inference-engine, Property 6: RLE decoder is bounded and typed
# **Validates: Requirements 1.9, 1.10, 1.11, 6.4**
@settings(max_examples=100, deadline=None)
@given(valid_rle_streams())
def test_property_6_valid_streams_decode_to_known_length(stream_and_len):
    stream, known = stream_and_len
    r = rle_pcx_decode(stream, 0, len(stream), known)
    assert r.status == "ok"
    assert len(r.data) == known
    assert r.consumed_to == len(stream)


# Feature: structure-inference-engine, Property 6: RLE decoder is bounded and typed
# **Validates: Requirements 1.9, 1.10, 1.11, 6.4**
@settings(max_examples=100, deadline=None)
@given(
    data=st.binary(max_size=65536),
    width=st.integers(),
    height=st.integers(),
    bit_depth=st.integers(),
    header_size=st.integers(),
    row_alignment=st.integers(),
    encoding=st.sampled_from(["none", "rle_pcx", "rle_tga", "x"]),
    data_end=st.one_of(st.none(), st.integers()),
    probe_name=st.sampled_from(["pcx", "tga", "pbm", "tiff", "generic"]),
)
def test_property_6_check_closure_never_raises(
    data, width, height, bit_depth, header_size, row_alignment,
    encoding, data_end, probe_name,
):
    h = Hypothesis(
        width=width, height=height, bit_depth=bit_depth, header_size=header_size,
        row_alignment=row_alignment, encoding=encoding, data_end=data_end,
        probe_name=probe_name,
    )
    v = check_closure(h, data)
    assert isinstance(v, ClosureVerdict)
    if not v.ok:
        assert v.decoded is None
        assert v.reason in REASONS


# ------------------------------------------- Req 12: header and data disjoint
import struct as _struct
from necropsy.engine import Engine
from necropsy.engine.types import FieldRecord


def _fr(offset, fmt="<H"):
    return FieldRecord("f", offset, fmt, (0,) * len(_struct.unpack(fmt, bytes(_struct.calcsize(fmt)))))


def _h12(fields, header_size=4, data_end=None):
    return Hypothesis(width=4, height=4, bit_depth=8, header_size=header_size,
                      data_end=data_end, fields=tuple(fields))


def test_req12_1_field_inside_data_region_rejected():
    # data [4, 20); field [10, 12) lies inside it
    v = check_closure(_h12([_fr(10)]), bytes(20))
    assert not v.ok and v.reason == "degenerate_hypothesis"


def test_req12_1_field_straddling_data_start_rejected():
    # data [4, 20); field [3, 5) crosses data_start
    v = check_closure(_h12([_fr(3)]), bytes(20))
    assert not v.ok and v.reason == "degenerate_hypothesis"


def test_req12_3_field_after_data_region_not_rejected():
    # data [4, 20) declared; field [20, 22) is after it
    v = check_closure(_h12([_fr(20)], data_end=20), bytes(22))
    assert v.ok


def test_req12_half_open_field_ending_at_data_start_not_rejected():
    # field [2, 4) ends exactly at data_start 4
    v = check_closure(_h12([_fr(2)]), bytes(20))
    assert v.ok


def test_req12_4_no_fields_unaffected():
    assert check_closure(_h12([]), bytes(20)).ok


def test_req12_bad_fmt_does_not_raise():
    bad = FieldRecord("f", 0, "not-a-fmt", ())
    v = check_closure(_h12([bad]), bytes(20))
    assert not v.ok


def _tiff_82_no_stripoffsets() -> bytes:
    def entry(tag, typ, val):
        if typ == 3:
            return _struct.pack(">HHIHH", tag, typ, 1, val, 0)
        return _struct.pack(">HHII", tag, typ, 1, val)
    d = _struct.pack(">2sHIH", b"MM", 42, 8, 6)
    d += entry(256, 3, 5) + entry(257, 3, 8) + entry(258, 3, 7)
    d += bytes(12) + bytes(12) + entry(279, 4, 0x40)
    return d.ljust(82, b"\0")


def test_req12_tiff_without_stripoffsets_no_longer_resolves_overlapping():
    data = _tiff_82_no_stripoffsets()
    assert len(data) == 82
    r = Engine().run(data)
    assert not (r.status == "RESOLVED"
                and (r.candidate.data_start, r.candidate.data_end) == (0, 64))


# --- Requirement 1.15 / 1.16: TGA 2.0 footer declared offsets -------------------
# Layout (all little-endian): type-3 TGA header, 18 bytes: id_length=0 @0, colour_map_type=0 @1,
# image_type=3 @2, colour map spec (5 bytes) @3, x/y origin @8..12, width <H @12, height <H @14,
# bit_depth @16, descriptor @17. Pixels: 64 bytes at [18, 82). Footer: 26 bytes
# (extension_area_offset <I @0, developer_area_offset <I @4, "TRUEVISION-XFILE.\0" @8).
# Extension area: 495 bytes, extension_size <H @0, colour_correction_offset <I @482,
# postage_stamp_offset <I @486, scan_line_offset <I @490.

import struct as _struct

_TGA_HEADER = bytes([0, 0, 3]) + bytes(5) + bytes(4) + _struct.pack("<HH", 8, 8) + bytes([8, 0])
_TGA_PIXELS = bytes((i * 7 + 3) % 256 for i in range(64))
_SIG = b"TRUEVISION-XFILE.\x00"


def _tga2(ext_off=0, dev_off=0, middle=b"", ext=None):
    """header + pixels + middle + (extension area) + footer; offsets are as given, not computed."""
    footer = _struct.pack("<II", ext_off, dev_off) + _SIG
    return _TGA_HEADER + _TGA_PIXELS + middle + (ext or b"") + footer


def _ext(size=495, colour=0, postage=0, scan=0):
    b = bytearray(495)
    _struct.pack_into("<H", b, 0, size)
    _struct.pack_into("<I", b, 482, colour)
    _struct.pack_into("<I", b, 486, postage)
    _struct.pack_into("<I", b, 490, scan)
    return bytes(b)


def _assert_tga_resolved(data, length):
    assert len(data) == length
    r = Engine().run(data)
    assert r.status == "RESOLVED"
    assert (r.candidate.data_start, r.candidate.data_end) == (18, 82)
    assert r.candidate.decoded == _TGA_PIXELS


def _assert_tga_oob(data, length):
    assert len(data) == length
    r = Engine().run(data)
    assert r.status != "RESOLVED"
    assert any(e.reason == "field_out_of_bounds" and e.source == "tga" for e in r.rejections)


def test_tga2_both_offsets_zero_req_1_16():
    _assert_tga_resolved(_tga2(), 108)


def test_tga2_developer_offset_req_1_16():
    _assert_tga_resolved(_tga2(dev_off=82, middle=bytes(10)), 118)


def test_tga2_extension_postage_stamp_req_1_16():
    _assert_tga_resolved(_tga2(ext_off=94, middle=bytes(12), ext=_ext(postage=82)), 615)


def test_tga2_extension_scan_line_req_1_16():
    _assert_tga_resolved(_tga2(ext_off=94, middle=bytes(12), ext=_ext(scan=82)), 615)


def test_tga2_extension_colour_correction_req_1_16():
    _assert_tga_resolved(_tga2(ext_off=94, middle=bytes(12), ext=_ext(colour=82)), 615)


def test_tga2_extension_offset_is_minimum_req_1_16():
    _assert_tga_resolved(_tga2(ext_off=82, ext=_ext()), 603)


def test_tga2_developer_offset_below_header_req_1_16():
    _assert_tga_oob(_tga2(dev_off=10), 108)


def test_tga2_developer_offset_equals_footer_start_req_1_16():
    _assert_tga_oob(_tga2(dev_off=82), 108)  # F = 82


def test_tga2_extension_size_494_req_1_16():
    _assert_tga_oob(_tga2(ext_off=82, ext=_ext(size=494)), 603)


def test_tga2_extension_size_496_overruns_footer_req_1_16():
    _assert_tga_oob(_tga2(ext_off=82, ext=_ext(size=496)), 603)  # 82 + 496 > 577


def test_tga2_postage_stamp_below_header_req_1_16():
    _assert_tga_oob(_tga2(ext_off=94, middle=bytes(12), ext=_ext(postage=10)), 615)


def test_trailer_data_end_never_raises_on_junk_req_1_15():
    from necropsy.engine.trailers import trailer_data_end
    assert trailer_data_end(b"", 0, "tga") == (0, None, None)
    assert trailer_data_end(_tga2(), 18, "pcx") == (108, None, None)


# ------------------------------------- Req 1.15 / task 18.5: Generic Search records footer rejections
# Headerless 90-byte file: 64 zero data bytes [0, 64), then a 26-byte TGA 2.0 footer at F = 64:
# extension_area_offset <I @64 = 70 (inside the footer [64, 90)), developer_area_offset <I @68 = 0,
# "TRUEVISION-XFILE.\0" @72. Header lengths are 4..256 step 4 below the file length; those with
# L <= 64 (4, 8, ..., 64: 16 values) match the footer entry and fail on the offset.

# Feature: structure-inference-engine, Property 17: Readings are complete
# **Validates: Requirements 1.17, 4.10, 6.4**
@st.composite
def _readings_inputs(draw):
    body = draw(st.binary(max_size=900))
    plant = draw(st.sampled_from(["none", "pcx", "tga"]))
    if plant == "pcx":
        body += b"\x0c" + draw(st.binary(min_size=768, max_size=768))
    elif plant == "tga":
        body += draw(st.binary(min_size=8, max_size=8)) + b"TRUEVISION-XFILE.\x00"
    header_size = draw(st.integers(-5, 1000))
    origin = draw(st.sampled_from(["pcx", "tga", "pbm", "tiff", "generic"]))
    data_end = draw(st.one_of(st.none(), st.integers(-5, 3000)))
    return body, header_size, origin, data_end


@settings(max_examples=100, deadline=None)
@given(_readings_inputs())
def test_property_17_readings_are_complete(args):
    from dataclasses import replace
    from necropsy.engine.closure import readings
    data, header_size, origin, data_end = args
    h = Hypothesis(width=4, height=4, bit_depth=8, header_size=header_size,
                   data_end=data_end, probe_name=origin)
    out = readings(h, data)
    matched = match_trailer(data, header_size, origin)[1] is not None
    if data_end is None and matched:
        assert out == (h, replace(h, data_end=len(data)))
        assert out[0].data_end is None
    else:
        assert out == (h,)


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=2000), st.integers(), st.sampled_from(["pcx", "tga", "generic", "x"]))
def test_property_17_readings_never_raises_on_arbitrary_bytes(data, header_size, origin):
    from necropsy.engine.closure import readings
    h = Hypothesis(width=4, height=4, bit_depth=8, header_size=header_size, probe_name=origin)
    out = readings(h, data)
    assert isinstance(out, tuple) and out[0] == h and len(out) in (1, 2)


def test_generic_records_footer_rejections_req_1_15():
    data = bytes(64) + _struct.pack("<II", 70, 0) + _SIG
    assert len(data) == 90
    from necropsy.engine.probes import PROBES
    for _name, probe in PROBES:  # no probe may match this file
        o = probe(data)
        assert o is None or (o.seed is None and o.rejections == ())
    r = Engine().run(data)
    assert r.status == "FAILED"
    expected = [
        f"header_length {L}: extension_area_offset = 70 not in [{L}, 64)"
        for L in range(4, 65, 4)
    ]
    assert len(expected) == 16
    assert len(r.rejections) == 16
    for e, detail in zip(r.rejections, expected):
        assert e.reason == "field_out_of_bounds"
        assert e.source == "generic"
        assert e.hypothesis is None
        assert e.detail == detail
    assert r.total_checks == 0
