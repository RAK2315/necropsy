"""Task 17 (format-coverage): several data ranges, strips (Requirements 7.5 to 7.8, 7.10 to 7.12, 15.1, 15.5).

Hypothesis objects are built directly; no probe emits ranges yet.
Layout: width 4, bit_depth 8, stride 4. Height 5, rows_per_strip 2 -> strips of 2, 2, 1 rows.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from necropsy.engine.closure import ClosureVerdict, check_closure
from necropsy.engine.types import FieldRecord, Hypothesis

HEADER = 8
DATA = bytes(range(8)) + bytes(range(100, 120))  # 8 header bytes + 20 pixel bytes
RANGES = ((8, 16), (16, 24), (24, 28))           # 8, 8, 4 bytes


def hyp(ranges=RANGES, height=5, rps=2, fields=(), width=4, **kw):
    return Hypothesis(width=width, height=height, bit_depth=8, header_size=min((s for s, _ in ranges), default=0),
                      encoding="none", probe_name="tiff", ranges=ranges, rows_per_strip=rps,
                      fields=fields, **kw)


def test_concatenation_and_short_last_strip_req_7_8_7_12():
    v = check_closure(hyp(), DATA)
    assert v.ok and v.decoded == DATA[8:28]          # exact bytes, in order
    assert (v.data_start, v.data_end) == (8, 28)


def test_ranges_out_of_file_order_concatenate_in_range_order():
    # Strips stored in reverse file order: decoded bytes follow the range order, not the file order.
    r = ((20, 28), (12, 20), (8, 12))
    v = check_closure(hyp(ranges=r), DATA)
    assert v.ok and v.decoded == DATA[20:28] + DATA[12:20] + DATA[8:12]


def test_one_range_short_req_7_10_7_11():
    v = check_closure(hyp(ranges=((8, 16), (16, 23), (23, 27))), DATA)
    assert not v.ok and v.reason == "arithmetic_mismatch" and v.discrepancy == -1
    assert "range 1" in v.detail


def test_one_range_long_stops_at_first_failure():
    v = check_closure(hyp(ranges=((8, 17), (17, 25), (25, 28))), DATA)
    assert not v.ok and v.reason == "arithmetic_mismatch" and v.discrepancy == 1
    assert "range 0" in v.detail


def test_range_out_of_bounds_req_7_5():
    v = check_closure(hyp(ranges=((8, 16), (16, 24), (24, 29))), DATA)
    assert not v.ok and v.reason == "field_out_of_bounds" and "range 2" in v.detail


def test_range_over_header_field_req_7_6():
    f = FieldRecord("w", 18, "<H", (4,))                # bytes 18..20 sit inside range 1
    v = check_closure(hyp(fields=(f,)), DATA)
    assert not v.ok and v.reason == "degenerate_hypothesis" and "range 1" in v.detail and "w" in v.detail


def test_field_between_two_ranges_is_accepted_req_7_6():
    data = bytes(range(8)) + bytes(range(100, 108)) + b"\xAA\xBB" + bytes(range(110, 122))
    r = ((8, 16), (18, 26), (26, 30))
    f = FieldRecord("gap", 16, "<H", (0xBBAA,))
    v = check_closure(hyp(ranges=r, fields=(f,)), data)
    assert v.ok and v.decoded == data[8:16] + data[18:30]


def test_overlapping_ranges_req_7_7():
    v = check_closure(hyp(ranges=((8, 16), (12, 20), (20, 24))), DATA)
    assert not v.ok and v.reason == "degenerate_hypothesis" and "overlap" in v.detail


def test_wrong_strip_count_req_7_8():
    v = check_closure(hyp(ranges=((8, 16), (16, 28))), DATA)
    assert not v.ok and v.reason == "degenerate_hypothesis" and "3 strips" in v.detail


def test_huge_declared_height_allocates_nothing():
    v = check_closure(hyp(height=10 ** 15, rps=2), DATA)
    assert not v.ok and v.reason == "degenerate_hypothesis"


def test_single_range_unchanged_without_ranges():
    h = Hypothesis(width=4, height=5, bit_depth=8, header_size=8, encoding="none", probe_name="tiff")
    v = check_closure(h, DATA)
    assert v.ok and v.decoded == DATA[8:28]


_ints = st.integers(-5, 40)


@settings(max_examples=200, deadline=None)
@given(data=st.binary(max_size=64),
       ranges=st.lists(st.tuples(_ints, _ints), max_size=6).map(tuple),
       height=st.integers(-2, 10 ** 12), rps=st.one_of(st.none(), st.integers(-2, 10 ** 12)),
       width=st.integers(-2, 10), tile=st.one_of(st.none(), st.tuples(_ints, _ints)))
def test_never_raises_req_15_1(data, ranges, height, rps, width, tile):
    h = Hypothesis(width=width, height=height, bit_depth=8, header_size=0, encoding="none",
                   probe_name="tiff", ranges=ranges, rows_per_strip=rps, tile=tile)
    v = check_closure(h, data)
    assert isinstance(v, ClosureVerdict)
    assert v.reason != "internal_error"
