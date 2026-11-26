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


# --- rle_tga (format-coverage task 10; Requirements 5.2 to 5.7, 2.8 to 2.10) ---
from necropsy.engine.decoders import rle_tga_decode


def tga(body, pb, out, start=0, end=None):
    return rle_tga_decode(body, start, len(body) if end is None else end, pb, out)


def test_tga_run_packet():
    # 0x82 = run of 3; pixel 0xAA
    r = tga(bytes([0x82, 0xAA]), 1, 3)
    assert (r.status, r.data, r.consumed_to) == ("ok", b"\xaa\xaa\xaa", 2)


def test_tga_raw_packet():
    # 0x01 = raw of 2 pixels
    r = tga(bytes([0x01, 1, 2, 3, 4]), 2, 4)
    assert (r.status, r.data, r.consumed_to) == ("ok", bytes([1, 2, 3, 4]), 5)


def test_tga_packet_across_row_end_decodes():
    # 2x2 8bpp: run of 3 crosses end of row 0, then raw of 1.
    r = tga(bytes([0x82, 7, 0x00, 9]), 1, 4)
    assert r.status == "ok" and r.data == bytes([7, 7, 7, 9])


def test_tga_overrun_does_not_write_and_consumed_after_packet():
    r = tga(bytes([0x83, 5, 0x00, 1]), 1, 3)
    assert r.status == "overrun" and r.data is None and r.consumed_to == 2


def test_tga_overrun_raw():
    r = tga(bytes([0x02, 1, 2, 3]), 1, 2)
    assert r.status == "overrun" and r.consumed_to == 4


def test_tga_region_ends_inside_run_packet():
    r = tga(bytes([0x80]), 3, 3)
    assert r.status == "underrun" and r.consumed_to == 1


def test_tga_region_ends_inside_raw_packet():
    r = tga(bytes([0x02, 1, 2]), 1, 3)
    assert r.status == "underrun" and r.consumed_to == 3


def test_tga_output_short_is_underrun():
    r = tga(bytes([0x80, 5]), 1, 3)
    assert r.status == "underrun" and r.consumed_to == 2


def test_tga_leftover_byte_is_unconsumed():
    r = tga(bytes([0x80, 5, 0x00]), 1, 1)
    assert r.status == "unconsumed" and r.consumed_to == 2 and r.data is None


def test_tga_pixel_sizes_and_range_bounds():
    for pb in (1, 2, 3, 4):
        px = bytes(range(10, 10 + pb))
        r = tga(b"\xff" + bytes([0x81]) + px, pb, 2 * pb, start=1)
        assert r.status == "ok" and r.data == px * 2 and r.consumed_to == 2 + pb
    r = tga(b"\x80\x01", 1, 1, start=0, end=5)  # end beyond data
    assert r.status == "underrun" and r.consumed_to == 0
    assert tga(b"\x80\x01", 1, 1, start=2, end=1).status == "underrun"
    assert tga(b"\x80\x01", 1, -1).status == "underrun"


def test_tga_huge_run_does_not_allocate_beyond_bound():
    r = tga(bytes([0xFF]) + b"\x01" * 4, 4, 8)
    assert r.status == "overrun" and r.data is None


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=200), st.integers(-1, 5), st.integers(-3, 300))
def test_rle_tga_never_raises(data, pb, cap):
    r = rle_tga_decode(data, 0, len(data), pb, cap)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
    assert isinstance(r.consumed_to, int) and isinstance(r.detail, str)
    assert (r.data is not None) == (r.status == "ok")
    if r.data is not None:
        assert len(r.data) == cap


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=64), st.integers(-5, 80), st.integers(-5, 80))
def test_rle_tga_never_raises_on_arbitrary_range(data, s, e):
    r = rle_tga_decode(data, s, e, 3, 6)
    assert isinstance(r, DecodeResult) and r.status in STATUSES


# ---- packbits_decode (format-coverage Requirement 11, Task 23) ----
from necropsy.engine.decoders import packbits_decode  # noqa: E402


def pb(body, out, start=0, end=None):
    return packbits_decode(body, start, len(body) if end is None else end, out)


def test_packbits_literal_packet():  # Req 11.2: 0..127 copies n + 1 bytes
    r = pb(b"\x02abc", 3)
    assert (r.status, r.data, r.consumed_to) == ("ok", b"abc", 4)


def test_packbits_run_packet():  # Req 11.2: -127..-1 repeats the next byte 1 - n times
    r = pb(b"\xfdx", 4)
    assert (r.status, r.data) == ("ok", b"xxxx")
    assert pb(b"\x81x", 128).data == b"x" * 128  # n = -127
    assert pb(b"\xffx", 2).data == b"xx"  # n = -1


def test_packbits_0x80_is_a_noop_inside_the_stream():  # Req 11.2
    r = pb(b"\x00a\x80\x00b", 2)
    assert (r.status, r.data, r.consumed_to) == ("ok", b"ab", 5)


def test_packbits_trailing_0x80_is_a_leftover_byte():  # Req 11.6
    r = pb(b"\x00a\x80", 1)
    assert (r.status, r.consumed_to) == ("unconsumed", 2)


def test_packbits_padded_strip_fails():  # Req 11.6, 11.7
    r = pb(b"\x00a\x00\x00", 1)
    assert (r.status, r.consumed_to) == ("unconsumed", 2)


def test_packbits_overrun_does_not_write_and_consumes_the_packet():  # Req 11.4
    r = pb(b"\x00a\xfdb", 3)
    assert (r.status, r.data, r.consumed_to) == ("overrun", None, 4)
    r = pb(b"\x03abcd", 3)
    assert (r.status, r.consumed_to) == ("overrun", 5)


def test_packbits_underrun_inside_packet_and_short_output():  # Req 11.5
    assert (pb(b"\x03ab", 4).status, pb(b"\x03ab", 4).consumed_to) == ("underrun", 3)
    assert pb(b"\xfd", 4).status == "underrun"
    r = pb(b"\x00a", 3)
    assert (r.status, r.consumed_to) == ("underrun", 2)
    assert pb(b"", 1).status == "underrun"
    assert pb(b"\x80\x80", 1).status == "underrun"


def test_packbits_empty_output_with_empty_region_is_ok():
    assert pb(b"", 0).status == "ok"


def test_packbits_honours_start_and_end():
    r = pb(b"zz\x00ayy", 1, start=2, end=4)
    assert (r.status, r.data, r.consumed_to) == ("ok", b"a", 4)


def test_packbits_invalid_arguments_underrun_at_start():
    assert pb(b"ab", 1, start=5, end=9).status == "underrun"
    assert packbits_decode(b"ab", 0, 2, -1).status == "underrun"


def test_packbits_bomb_is_bounded_by_max_output_bytes():  # Req 11.3, 2.13
    body = b"\x81x" * 100000  # would expand to 12.8 MB
    r = pb(body, 1000)
    assert r.status == "overrun" and r.data is None


@given(st.binary(max_size=300), st.integers(-5, 400))
@settings(max_examples=200, deadline=None)
def test_packbits_never_raises(data, cap):
    r = packbits_decode(data, 0, len(data), cap)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
    if r.status == "ok":
        assert len(r.data) == cap


@given(st.binary(max_size=64), st.integers(-10, 100), st.integers(-10, 100))
@settings(max_examples=200, deadline=None)
def test_packbits_never_raises_on_arbitrary_range(data, s, e):
    r = packbits_decode(data, s, e, 8)
    assert isinstance(r, DecodeResult) and r.status in STATUSES


# ---- lzw_tiff_decode (format-coverage Requirement 12, Task 24) ----
import random  # noqa: E402
import time  # noqa: E402

from necropsy.engine.decoders import DECODE_CAP, lzw_tiff_decode  # noqa: E402

CLEAR, EOI = 256, 257


def pack_codes(codes):
    """Pack (code, width) pairs most significant bit first; zero padding bits fill the last byte."""
    acc = nbits = 0
    for code, width in codes:
        acc = (acc << width) | code
        nbits += width
    pad = -nbits % 8
    return (acc << pad).to_bytes((nbits + pad) // 8, "big")


def lzw_encode_codes(data):
    """Documented TIFF 6.0 LZW encoder, independent of the decoder: (code, width) pairs.

    Table starts at 258 entries (0..255 literals, 256 CLEAR, 257 EOI). After each emitted code the
    entry w + next byte is added while fewer than 4094 entries exist; when 4094 are held the code is
    followed by CLEAR and the table resets. The width grows after entry 510, 1022 and 2046 is added
    (the table then holds 511, 1023, 2047 entries) and applies to the next code written.
    """
    out = [(CLEAR, 9)]
    width, free = 9, 258
    table = {bytes((i,)): i for i in range(256)}
    w = b""
    for b in data:
        wc = w + bytes((b,))
        if wc in table:
            w = wc
            continue
        out.append((table[w], width))
        if free < 4094:
            table[wc] = free
            free += 1
            if free in (512, 1024, 2048):
                width += 1
        else:
            out.append((CLEAR, width))
            table = {bytes((i,)): i for i in range(256)}
            free, width = 258, 9
        w = bytes((b,))
    if w:
        out.append((table[w], width))
        if free < 4094:
            free += 1
            if free in (512, 1024, 2048):
                width += 1
    out.append((EOI, width))
    return out


def lzw_encode(data):
    return pack_codes(lzw_encode_codes(data))


def lzw(body, out, start=0, end=None):
    return lzw_tiff_decode(body, start, len(body) if end is None else end, out)


def test_lzw_stream_that_ends_exactly_is_ok():  # Req 12.10
    data = b"abcabcabcabc" * 3
    enc = lzw_encode(data)
    r = lzw(enc, len(data))
    assert (r.status, r.data, r.consumed_to) == ("ok", data, len(enc))


def test_lzw_one_extra_byte_after_eoi_is_unconsumed():  # Req 12.9, 12.10
    enc = lzw_encode(b"hello")
    r = lzw(enc + b"\x00", 5)
    assert (r.status, r.consumed_to) == ("unconsumed", len(enc))


def test_lzw_padding_bits_in_the_last_byte_are_not_leftover():  # Req 12.9
    enc = pack_codes([(CLEAR, 9), (97, 9), (EOI, 9)])  # 27 bits, 5 padding bits
    assert len(enc) == 4
    r = lzw(enc, 1)
    assert (r.status, r.data, r.consumed_to) == ("ok", b"a", 4)


def test_lzw_cut_before_eoi_is_underrun_at_end():  # Req 12.8
    enc = pack_codes([(CLEAR, 9), (97, 9), (EOI, 9)])[:-1]
    r = lzw(enc, 1)
    assert (r.status, r.consumed_to) == ("underrun", len(enc))


def test_lzw_eoi_with_short_output_is_underrun_after_the_eoi_byte():  # Req 12.10
    enc = pack_codes([(CLEAR, 9), (97, 9), (EOI, 9)])
    r = lzw(enc, 2)
    assert (r.status, r.consumed_to) == ("underrun", 4)


def test_lzw_code_above_the_table_is_malformed():  # Req 12.5, 12.6
    # Table holds 258 entries; after 'a' it still holds 258, so 300 is above it. Bits read: 27.
    enc = pack_codes([(CLEAR, 9), (97, 9), (300, 9), (EOI, 9)])
    r = lzw(enc, 5)
    assert (r.status, r.consumed_to) == ("malformed", 4)
    assert "300" in r.detail


def test_lzw_first_code_must_be_clear_or_literal():  # Req 12.3
    enc = pack_codes([(CLEAR, 9), (258, 9), (EOI, 9)])
    assert lzw(enc, 1).status == "malformed"
    assert lzw(pack_codes([(258, 9), (EOI, 9)]), 1).status == "malformed"


def test_lzw_code_equal_to_table_size_repeats_the_first_byte():  # Req 12.5
    enc = pack_codes([(CLEAR, 9), (97, 9), (258, 9), (EOI, 9)])  # 'a', then 'a' + 'a'
    r = lzw(enc, 3)
    assert (r.status, r.data) == ("ok", b"aaa")


def test_lzw_output_one_byte_too_long_is_overrun_without_writing():  # Req 12.7
    enc = pack_codes([(CLEAR, 9), (97, 9), (98, 9), (99, 9), (100, 9), (EOI, 9)])  # 45 bits read at the 5th code
    r = lzw(enc, 3)
    assert (r.status, r.data, r.consumed_to) == ("overrun", None, 6)


def test_lzw_crosses_every_code_width_and_a_clear_in_the_middle():  # Req 12.4, 12.12
    data = bytes(random.Random(7).choices(range(4), k=40000))
    codes = lzw_encode_codes(data)
    assert {w for _, w in codes} == {9, 10, 11, 12}
    assert [c for c, _ in codes].count(CLEAR) >= 2  # the first, and a mid-stream one when the table is full
    enc = pack_codes(codes)
    r = lzw(enc, len(data))
    assert (r.status, r.data, r.consumed_to) == ("ok", data, len(enc))


def test_lzw_no_data_stream_is_empty_output():
    enc = lzw_encode(b"")
    assert lzw(enc, 0).status == "ok" and lzw(enc, 0).data == b""


def zeros_stream_codes(cycles):
    """Codes for a run of zeros that expands as much as the table allows, from the encoder's rules:
    per cycle emission 1 is literal 0 and emission j >= 2 is entry 258 + j - 2 (a run of j zeros);
    emission j is 9 bits up to j = 254, 10 up to 766, 11 up to 1790, then 12; emission 3837 is
    followed by CLEAR at 12 bits."""
    codes = [(CLEAR, 9)]
    for _ in range(cycles):
        for j in range(1, 3838):
            width = 9 if j <= 254 else 10 if j <= 766 else 11 if j <= 1790 else 12
            codes.append((0 if j == 1 else 258 + j - 2, width))
        codes.append((CLEAR, 12))
    return codes


def test_lzw_first_cycle_of_the_expanding_stream_decodes_to_zeros():
    codes = zeros_stream_codes(1)[:-1] + [(EOI, 12)]
    total = 3837 * 3838 // 2
    r = lzw(pack_codes(codes), total)
    assert r.status == "ok" and r.data == bytes(total)


def test_lzw_worst_case_expansion_returns_within_two_seconds():  # Req 15.3
    stream = pack_codes(zeros_stream_codes(13))
    assert len(stream) >= 65536
    stream = stream[:65536]
    t0 = time.perf_counter()
    r = lzw(stream, DECODE_CAP)
    elapsed = time.perf_counter() - t0
    assert r.status == "overrun" and r.data is None
    assert elapsed < 2.0, elapsed


def test_lzw_bomb_is_bounded_by_max_output_bytes():  # Req 12.11, 15.4
    stream = pack_codes(zeros_stream_codes(1))
    for cap in (0, 1, 1000):
        r = lzw(stream, cap)
        assert r.status == "overrun" and r.data is None


def test_lzw_honours_start_and_end_and_invalid_arguments():
    enc = lzw_encode(b"xyz")
    r = lzw(b"zz" + enc + b"yy", 3, start=2, end=2 + len(enc))
    assert (r.status, r.data, r.consumed_to) == ("ok", b"xyz", 2 + len(enc))
    assert lzw(enc, 3, start=5, end=9).status == "underrun"
    assert lzw_tiff_decode(enc, 0, len(enc), -1).status == "underrun"


@given(st.binary(max_size=300), st.integers(-5, 5000))
@settings(max_examples=200, deadline=None)
def test_lzw_never_raises(data, cap):
    r = lzw_tiff_decode(data, 0, len(data), cap)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
    if r.status == "ok":
        assert len(r.data) == cap
    else:
        assert r.data is None


@given(st.binary(max_size=64), st.integers(-10, 100), st.integers(-10, 100))
@settings(max_examples=200, deadline=None)
def test_lzw_never_raises_on_arbitrary_range(data, s, e):
    r = lzw_tiff_decode(data, s, e, 8)
    assert isinstance(r, DecodeResult) and r.status in STATUSES
