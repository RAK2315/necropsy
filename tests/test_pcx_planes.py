"""PCX multi-plane seed (format-coverage Task 15; Requirements 6.1, 6.2, 6.6, 6.7, 6.8, 15.1).

Fixtures are built from the documented PCX header layout (design.md "PCX"):
0x00 0x0A signature, 0x02 encoding, 0x03 bits per plane, 0x04 <HHHH xmin ymin xmax ymax,
0x41 planes, 0x42 <H bytes_per_line.
"""
import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.probes import probe_pcx


def pcx(encoding, bpp, xmax, ymax, planes, bpl, body):
    h = bytearray(128)
    h[0x00] = 0x0A
    h[0x01] = 5
    h[0x02] = encoding
    h[0x03] = bpp
    struct.pack_into("<HHHH", h, 0x04, 0, 0, xmax, ymax)
    h[0x41] = planes
    struct.pack_into("<H", h, 0x42, bpl)
    return bytes(h) + body


# 3 planes x 8 bits, 4 x 2 pixels, bytes_per_line 4. RLE: 0xC4 0x07 is four 7s.
R0, G0, B0 = [1, 2, 3, 4], [7, 7, 7, 7], [9, 8, 7, 6]
R1, G1, B1 = [10, 11, 12, 13], [20, 21, 22, 23], [5, 5, 5, 5]
RGB_BODY = bytes(R0) + bytes([0xC4, 7]) + bytes(B0) + bytes(R1) + bytes(G1) + bytes([0xC4, 5])
RGB_DECODED = bytes(R0 + G0 + B0 + R1 + G1 + B1)


def test_three_plane_seed_fields():
    out = probe_pcx(pcx(1, 8, 3, 1, 3, 4, RGB_BODY))
    s = out.seed
    assert (s.planes, s.row_bytes, s.bit_depth) == (3, 12, 24)  # 3 x 4; 8 x 3
    assert (s.width, s.height) == (3, 1)  # naive, before inclusive_bounds


def test_three_plane_rle_resolves_with_exact_scanlines():
    r = Engine().run(pcx(1, 8, 3, 1, 3, 4, RGB_BODY))
    assert r.status == "RESOLVED"
    c = r.candidate
    h = c.hypothesis
    assert tuple(h.revision_path) == ("inclusive_bounds",)
    assert (h.width, h.height, h.bit_depth, h.planes, h.row_bytes) == (4, 2, 24, 3, 12)
    assert c.row_stride == 12 and c.expected_decoded_bytes == 24
    assert c.decoded == RGB_DECODED


def test_four_plane_one_bit_resolves_with_exact_scanlines():
    # 8 x 2 pixels, 1 bit per plane, bytes_per_line 1: scanline = 4 bytes (plane 0..3).
    body = bytes([0x81, 0x42, 0x24, 0x18, 0xFF & 0x3F, 0x01, 0x02, 0x03])
    r = Engine().run(pcx(1, 1, 7, 1, 4, 1, body))
    assert r.status == "RESOLVED"
    h = r.candidate.hypothesis
    assert tuple(h.revision_path) == ("inclusive_bounds",)
    assert (h.width, h.height, h.bit_depth, h.planes, h.row_bytes) == (8, 2, 4, 4, 4)
    assert r.candidate.decoded == body


def test_single_plane_seed_unchanged():
    s = probe_pcx(pcx(0, 8, 7, 7, 1, 8, b"")).seed
    assert (s.planes, s.row_bytes, s.bit_depth) == (1, None, 8)


def test_planes_zero_unchanged():
    s = probe_pcx(pcx(0, 8, 7, 7, 0, 8, b"")).seed
    assert (s.planes, s.row_bytes, s.bit_depth) == (1, None, 8)


def test_multi_plane_bytes_per_line_zero_is_recorded_and_fails_closure():
    out = probe_pcx(pcx(0, 8, 3, 1, 3, 0, b"\x00" * 24))
    assert out.seed.row_bytes == 0
    assert any(x.reason == "probe_precondition_failed" for x in out.rejections)
    assert Engine().run(pcx(0, 8, 3, 1, 3, 0, b"\x00" * 24)).status == "FAILED"


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=600))
def test_pcx_probe_never_raises(b):
    out = probe_pcx(b)
    assert out is None or hasattr(out, "seed")


@settings(max_examples=200, deadline=None)
@given(st.integers(2, 255), st.integers(0, 255), st.integers(0, 1), st.binary(max_size=200))
def test_pcx_multi_plane_header_never_raises(planes, bpl, enc, body):
    out = probe_pcx(pcx(enc, 8, 5, 5, planes, bpl, body))
    assert out is not None
    assert out.seed.row_bytes == planes * bpl
