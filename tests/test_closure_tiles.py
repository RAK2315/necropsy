"""Task 20 (format-coverage): tile assembly (Requirements 7.9, 7.12, 9.6, 15.1).

Hypothesis objects are built directly. Tile bytes are built from a per-pixel function:
pixel (x, y) of the image is 10*y + x; a position beyond the image edge holds 200.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from necropsy.engine.closure import ClosureVerdict, check_closure
from necropsy.engine.types import Hypothesis


def pix(x, y, w, h):
    return 10 * y + x if x < w and y < h else 200


def build(w, h, tw, tl, bpp=1, prefix=4):
    """Return (data, ranges, expected image) for a tile grid of bpp bytes per pixel, tiles stored in order."""
    across, down = -(-w // tw), -(-h // tl)
    data = bytearray(range(prefix))
    ranges = []
    for ty in range(down):
        for tx in range(across):
            start = len(data)
            for r in range(tl):
                for c in range(tw):
                    v = pix(tx * tw + c, ty * tl + r, w, h)
                    data += bytes([(v + k) % 256 for k in range(bpp)])
            ranges.append((start, len(data)))
    img = bytearray()
    for y in range(h):
        for x in range(w):
            img += bytes([(pix(x, y, w, h) + k) % 256 for k in range(bpp)])
    return bytes(data), tuple(ranges), bytes(img)


def hyp(w, h, tw, tl, ranges, bit_depth=8, **kw):
    return Hypothesis(width=w, height=h, bit_depth=bit_depth, header_size=min((s for s, _ in ranges), default=0),
                      encoding="none", probe_name="tiff", ranges=ranges, tile=(tw, tl), **kw)


def test_partial_last_column_and_row_every_byte_req_7_9_7_12():
    data, ranges, img = build(5, 3, 2, 2)           # 3 x 2 tiles, last column 1 px wide, last row 1 row high
    assert len(ranges) == 6
    v = check_closure(hyp(5, 3, 2, 2, ranges), data)
    assert v.ok and v.decoded == img and len(v.decoded) == 15
    assert (v.data_start, v.data_end) == (4, len(data))


def test_exact_grid_and_tiles_out_of_file_order():
    data, ranges, img = build(4, 4, 2, 2)
    # Tile 0 at the end of the file, others in order: the decoded image follows range order.
    r = list(ranges)
    r[0], r[3] = r[3], r[0]
    v = check_closure(hyp(4, 4, 2, 2, tuple(r)), data)
    assert v.ok and v.decoded != img
    # Swapping tiles 0 and 3 swaps those quadrants: pixel (0,0) now holds tile 3's top-left pixel.
    assert v.decoded[0] == pix(2, 2, 4, 4) and v.decoded[10] == pix(0, 0, 4, 4)


def test_24_bit_tiles_req_7_9():
    data, ranges, img = build(3, 3, 2, 2, bpp=3)
    v = check_closure(hyp(3, 3, 2, 2, ranges, bit_depth=24), data)
    assert v.ok and v.decoded == img and len(v.decoded) == 27


def test_1_bit_tiles_byte_aligned_width_req_7_9():
    # Width 10, height 3, tile 8 x 2 at 1 bit: tile row is 1 byte, tiles 2 bytes; grid 2 x 2; stride 2.
    tile_bytes = [b"\xA5\x5A", b"\xC0\x30", b"\xFF\x00", b"\x80\x80"]
    data = b"\x00\x01\x02\x03" + b"".join(tile_bytes)
    ranges = tuple((4 + 2 * i, 6 + 2 * i) for i in range(4))
    v = check_closure(hyp(10, 3, 8, 2, ranges, bit_depth=1), data)
    # Image rows (stride 2): row 0 = t0 row0, t1 row0; row 1 = t0 row1, t1 row1; row 2 = t2 row0, t3 row0.
    assert v.ok and v.decoded == b"\xA5\xC0" + b"\x5A\x30" + b"\xFF\x80"


def test_tile_width_not_byte_aligned_rejected_req_7_9():
    data, ranges, _ = build(4, 2, 4, 2)
    v = check_closure(hyp(4, 2, 4, 2, ranges, bit_depth=1), data)    # 4 x 1 mod 8 != 0
    assert not v.ok and v.reason == "degenerate_hypothesis" and "byte" in v.detail


def test_wrong_tile_count_rejected_req_7_9():
    data, ranges, _ = build(5, 3, 2, 2)
    v = check_closure(hyp(5, 3, 2, 2, ranges[:5]), data)
    assert not v.ok and v.reason == "degenerate_hypothesis" and "6 tiles" in v.detail


def test_one_tile_wrong_length_req_7_10():
    data, ranges, _ = build(4, 2, 2, 2)
    r = (ranges[0], (ranges[1][0], ranges[1][1] - 1))
    v = check_closure(hyp(4, 2, 2, 2, r), data)
    assert not v.ok and v.reason == "arithmetic_mismatch" and v.discrepancy == -1 and "range 1" in v.detail


def test_assembled_size_checked_against_cap_before_allocation_req_9_6():
    # Two 1-byte-wide tiles cannot cover an image of 10**9 x 10 bytes; declared size is huge but
    # the count check fails first. With the count matching, the cap check rejects before allocating.
    from necropsy.engine.decoders import DECODE_CAP
    w, h = 4096, 4096                                  # 16 MiB assembled, tiles of one full image
    assert w * h > DECODE_CAP
    ranges = ((0, w * h),)
    v = check_closure(hyp(w, h, w, h, ranges), bytes(w * h))
    assert not v.ok and v.reason == "degenerate_hypothesis" and "cap" in v.detail


def test_encoding_other_than_none_still_unsupported():
    data, ranges, _ = build(4, 2, 2, 2)
    h = hyp(4, 2, 2, 2, ranges)
    from dataclasses import replace
    v = check_closure(replace(h, encoding="packbits"), data)
    assert not v.ok and v.reason in ("unsupported_encoding", "degenerate_hypothesis")


_ints = st.integers(-5, 40)


@settings(max_examples=300, deadline=None)
@given(data=st.binary(max_size=96),
       ranges=st.lists(st.tuples(_ints, _ints), max_size=8).map(tuple),
       width=st.integers(-2, 12), height=st.integers(-2, 12), bit_depth=st.sampled_from([1, 8, 16, 24]),
       tile=st.tuples(st.integers(-2, 14), st.integers(-2, 14)),
       huge=st.booleans())
def test_never_raises_req_15_1(data, ranges, width, height, bit_depth, tile, huge):
    if huge:
        width, height = width * 10 ** 9, height * 10 ** 9
    h = Hypothesis(width=width, height=height, bit_depth=bit_depth, header_size=0, encoding="none",
                   probe_name="tiff", ranges=ranges, tile=tile)
    v = check_closure(h, data)
    assert isinstance(v, ClosureVerdict)
    assert v.reason != "internal_error"
