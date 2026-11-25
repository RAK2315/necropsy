"""Task 13 (format-coverage): declared row bytes and planes in the closure gate (Requirements 6.3, 6.4, 6.7, 15.1).

Hypothesis objects are built directly; the PCX probe does not set these fields yet.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from necropsy.engine.closure import ClosureVerdict, check_closure, hypothesis_row_stride
from necropsy.engine.types import Hypothesis


def hyp(width, height, bit_depth, planes, row_bytes, alignment=1, encoding="none"):
    return Hypothesis(width=width, height=height, bit_depth=bit_depth, header_size=0,
                      row_alignment=alignment, encoding=encoding, planes=planes,
                      row_bytes=row_bytes, probe_name="pnm")


def test_row_bytes_replaces_derived_stride_req_6_3():
    # 2 px, 3 planes of 8 bits, bytes_per_line 4: row_bytes = 12, derived stride would be 6.
    h = hyp(2, 2, 24, 3, 12)
    assert hypothesis_row_stride(h) == 12
    data = bytes(range(24))
    v = check_closure(h, data)
    assert v.ok and v.decoded == data
    # 12 bytes would close under the derived stride 6 x 2 but not under 12 x 2.
    v = check_closure(h, data[:12])
    assert not v.ok and v.reason == "arithmetic_mismatch" and v.discrepancy == -12


def test_row_alignment_is_ignored_req_6_3():
    # Alignment 4 would give a stride of 8; the declared 6 is used.
    h = hyp(2, 2, 24, 3, 6, alignment=4)
    assert hypothesis_row_stride(h) == 6
    assert check_closure(h, bytes(12)).ok


def test_bit_depth_not_multiple_of_planes_req_6_4():
    v = check_closure(hyp(2, 2, 8, 3, 6), bytes(12))
    assert not v.ok and v.reason == "degenerate_hypothesis" and v.detail


def test_bytes_per_line_too_small_req_6_4():
    # 2 px x 8 bits x 3 planes needs 6 bytes per scanline; 5 cannot hold it.
    v = check_closure(hyp(2, 2, 24, 3, 5), bytes(10))
    assert not v.ok and v.reason == "degenerate_hypothesis" and v.detail
    # exactly the minimum is fine
    assert check_closure(hyp(2, 2, 24, 3, 6), bytes(12)).ok


def test_one_bit_planes_use_ceil_per_plane_req_6_4():
    # 9 px, 4 planes of 1 bit: each plane needs ceil(9/8) = 2 bytes, 8 per scanline.
    assert not check_closure(hyp(9, 1, 4, 4, 7), bytes(7)).ok
    assert check_closure(hyp(9, 1, 4, 4, 8), bytes(8)).ok


def test_rle_planar_region_req_6_7():
    # 0xCC = run marker, 12 copies of 7: two scanlines of 6 bytes.
    h = hyp(2, 2, 24, 3, 6, encoding="rle_pcx")
    v = check_closure(h, bytes([0xCC, 7]))
    assert v.ok and v.decoded == bytes([7]) * 12
    # one byte too few decoded: underrun
    v = check_closure(h, bytes([0xCB, 7]))
    assert not v.ok and v.reason == "decoder_underrun"


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=64), st.integers(-2, 70), st.integers(-2, 8),
       st.integers(-2, 70), st.sampled_from(["none", "rle_pcx"]))
def test_never_raises_req_15_1(data, row_bytes, planes, depth, enc):
    h = Hypothesis(width=3, height=2, bit_depth=depth, header_size=0, encoding=enc,
                   planes=planes, row_bytes=row_bytes, probe_name="pnm")
    assert isinstance(check_closure(h, data), ClosureVerdict)
