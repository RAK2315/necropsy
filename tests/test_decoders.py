"""Tests for necropsy/engine/decoders.py (format-coverage task 6)."""
from hypothesis import given, settings, strategies as st

from necropsy.engine.decoders import STATUSES, DecodeResult, pnm_text_decode


def dec(body, w, h, depth, maxval, out):
    return pnm_text_decode(body, 0, len(body), w, h, depth, maxval, out)


# --- P1 (Req 4.4, 4.6) ---
def test_p1_digit_runs_without_separators_ok():
    r = dec(b"10110010", 8, 1, 1, 1, 1)
    assert (r.status, r.data, r.consumed_to) == ("ok", bytes([0b10110010]), 8)


def test_p1_separators_and_comments_same_pixels():
    a = dec(b"1 0 1\n# c 1 1\n1 0 0", 3, 2, 1, 1, 2)
    b = dec(b"101100", 3, 2, 1, 1, 2)
    assert a.status == b.status == "ok"
    # rows are 101 and 100, each padded to a byte
    assert a.data == b.data == bytes([0b10100000, 0b10000000])


def test_p1_row_packing_pads_each_row():
    r = dec(b"1111111111", 5, 2, 1, 1, 2)  # two rows of 5 bits
    assert r.status == "ok" and r.data == bytes([0b11111000, 0b11111000])
    r = dec(b"111111111", 9, 1, 1, 1, 2)
    assert r.data == bytes([0xFF, 0x80])


def test_p1_digit_two_is_above_maxval():
    r = dec(b"1 2 0", 3, 1, 1, 1, 1)
    assert r.status == "above_maxval" and r.consumed_to == 3 and r.data is None
    assert "offset 2" in r.detail and "value 2" in r.detail and "maximum 1" in r.detail


def test_p1_letter_is_malformed():
    r = dec(b"1x0", 3, 1, 1, 1, 1)
    assert r.status == "malformed" and r.consumed_to == 1


# --- P2 / P3 ---
def test_p2_ok_8bit():
    r = dec(b" 0 7\n255 16 ", 2, 2, 8, 255, 4)
    assert r.status == "ok" and r.data == bytes([0, 7, 255, 16]) and r.consumed_to == 12


def test_p2_16bit_big_endian():
    r = dec(b"258 65535", 2, 1, 16, 65535, 4)
    assert r.status == "ok" and r.data == bytes([1, 2, 255, 255])


def test_p3_ok():
    r = dec(b"1 2 3 # x\n4 5 6", 2, 1, 24, 255, 6)
    assert r.status == "ok" and r.data == bytes([1, 2, 3, 4, 5, 6])


def test_p2_number_above_maxval():
    r = dec(b"1 16 3", 3, 1, 8, 15, 3)
    assert r.status == "above_maxval" and r.consumed_to == 4
    assert "value 16" in r.detail and "offset 2" in r.detail and "maximum 15" in r.detail


def test_p2_no_whitespace_run_is_above_maxval():
    r = dec(b"255255", 2, 1, 8, 255, 2)
    assert r.status == "above_maxval" and r.consumed_to == 6


def test_p2_non_digit_token_malformed():
    r = dec(b"1 2x 3", 3, 1, 8, 255, 3)
    assert r.status == "malformed" and r.consumed_to == 2


def test_six_digit_token_with_leading_zeros_ok_and_long_is_above():
    assert dec(b"000007", 1, 1, 8, 255, 1).data == bytes([7])
    r = dec(b"0000255", 1, 1, 8, 255, 1)
    assert r.status == "ok" and r.data == bytes([255])
    r = dec(b"1" + b"0" * 5000, 1, 1, 8, 255, 1)
    assert r.status == "above_maxval"


def test_underrun_short_file():
    r = dec(b"1 2", 3, 1, 8, 255, 3)
    assert r.status == "underrun" and r.consumed_to == 3
    r = dec(b"1 0", 3, 1, 1, 1, 1)
    assert r.status == "underrun" and r.consumed_to == 3


def test_unconsumed_extra_number_and_digit():
    r = dec(b"1 2 3 4", 3, 1, 8, 255, 3)
    assert r.status == "unconsumed" and r.consumed_to == 6
    r = dec(b"101 1 ", 3, 1, 1, 1, 1)
    assert r.status == "unconsumed" and r.consumed_to == 4
    r = dec(b"1 2 3 x", 3, 1, 8, 255, 3)
    assert r.status == "unconsumed" and r.consumed_to == 6


def test_trailing_whitespace_and_comments_ok():
    r = dec(b"1 2 3 \n# done\n\n", 3, 1, 8, 255, 3)
    assert r.status == "ok" and r.consumed_to == 15


def test_overrun_without_writing():
    r = dec(b"1 2 3", 3, 1, 8, 255, 2)
    assert r.status == "overrun" and r.consumed_to == 5 and r.data is None
    r = dec(b"1 1 1 1 1 1 1 1 1", 9, 1, 1, 1, 1)
    assert r.status == "overrun" and r.consumed_to == 17


def test_invalid_arguments_underrun_at_start():
    for args in ((-1, 3, 3, 1, 8, 255, 3), (0, 99, 3, 1, 8, 255, 3), (3, 1, 3, 1, 8, 255, 3), (0, 3, 3, 1, 8, 255, -1)):
        r = pnm_text_decode(b"1 2", *args)
        assert r.status == "underrun" and r.consumed_to == args[0] and r.data is None


def test_output_never_exceeds_bound_with_huge_declared_size():
    r = dec(b"1 2 3", 10**9, 10**9, 8, 255, 3)
    assert r.status in STATUSES and (r.data is None or len(r.data) <= 3)


# --- never raises ---
@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=200), st.integers(0, 6), st.integers(0, 6),
       st.sampled_from([1, 8, 16, 24, 48]), st.integers(0, 70000), st.integers(0, 100))
def test_pnm_text_never_raises(data, w, h, depth, maxval, cap):
    r = pnm_text_decode(data, 0, len(data), w, h, depth, maxval, cap)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
    assert isinstance(r.consumed_to, int) and isinstance(r.detail, str)
    assert (r.data is not None) == (r.status == "ok")
    if r.data is not None:
        assert len(r.data) == cap


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=64), st.integers(-5, 80), st.integers(-5, 80))
def test_pnm_text_never_raises_on_arbitrary_range(data, s, e):
    r = pnm_text_decode(data, s, e, 2, 2, 8, 255, 4)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
