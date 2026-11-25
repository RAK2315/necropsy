"""Task 11 (format-coverage): rle_tga registered in DECODERS (Requirements 5.8, 5.9, 5.10, 15.1)."""
from __future__ import annotations

import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.closure import ClosureVerdict, check_closure
from necropsy.engine.decoders import DECODERS
from necropsy.engine.types import REASONS, Hypothesis

# 18-byte TGA header: id_length 0 (0x00), colour map type 0 (0x01), image type 10 (0x02),
# width <H (0x0C), height <H (0x0E), bits per pixel (0x10), descriptor 0x20 = top-left (0x11).
PIXEL_A, PIXEL_B, PIXEL_C = b"\x01\x02\x03", b"\x04\x05\x06", b"\x07\x08\x09"
# 3 x 2 at 24 bpp. Packets: run of 4 x A (0x83; crosses the end of row 0), raw 2 pixels B, C (0x01).
BODY = b"\x83" + PIXEL_A + b"\x01" + PIXEL_B + PIXEL_C
PIXELS = PIXEL_A * 4 + PIXEL_B + PIXEL_C
# 26-byte TGA 2.0 footer: extension offset <I = 0, developer offset <I = 0, signature at 0x08.
FOOTER = struct.pack("<II", 0, 0) + b"TRUEVISION-XFILE.\x00"


def header(w=3, h=2, bpp=24, itype=10):
    b = bytearray(18)
    b[2] = itype
    struct.pack_into("<HH", b, 12, w, h)
    b[16] = bpp
    b[17] = 0x20
    return bytes(b)


def hyp(bit_depth=24, w=3, h=2, **kw):
    return Hypothesis(width=w, height=h, bit_depth=bit_depth, header_size=18,
                      encoding="rle_tga", probe_name="tga", **kw)


def test_registered_req_5_9():
    assert "rle_tga" in DECODERS


def test_gate_decodes_pixels_in_stored_order_req_5_10():
    v = check_closure(hyp(), header() + BODY)
    assert v.ok and v.decoded == PIXELS and (v.data_start, v.data_end) == (18, 18 + len(BODY))


def test_pixel_bytes_is_ceil_of_bit_depth_req_5_2():
    # 15-bit pixels occupy 2 bytes: 2 x 1 image, one run packet of 2.
    v = check_closure(hyp(bit_depth=15, w=2, h=1), header(2, 1, 15) + b"\x81\xAA\xBB")
    assert v.ok and v.decoded == b"\xAA\xBB" * 2


def test_footer_excluded_from_data_region_req_5_8():
    v = check_closure(hyp(), header() + BODY + FOOTER)
    assert v.ok and v.decoded == PIXELS and v.data_end == 18 + len(BODY)


def test_leftover_byte_without_footer_is_unconsumed_req_5_8():
    v = check_closure(hyp(), header() + BODY + b"\x00")
    assert not v.ok and v.reason == "decoder_unconsumed"


def test_engine_resolves_rle_tga_with_footer_req_5_8():
    r = Engine().run(header() + BODY + FOOTER)
    assert r.status == "RESOLVED"
    c = r.candidate
    assert c.hypothesis.encoding == "rle_tga" and c.decoded == PIXELS


@settings(max_examples=150, deadline=None)
@given(data=st.binary(max_size=200), bpp=st.sampled_from([1, 8, 15, 16, 24, 32]),
       w=st.integers(-1, 6), h=st.integers(-1, 6))
def test_rle_tga_gate_never_raises_req_15_1(data, bpp, w, h):
    v = check_closure(hyp(bpp, w, h), data)
    assert isinstance(v, ClosureVerdict)
    if not v.ok:
        assert v.reason in REASONS and v.decoded is None
