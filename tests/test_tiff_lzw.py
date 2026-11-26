"""LZW TIFF through the engine (format-coverage Requirement 12, Task 24).

2 x 5 grey image, RowsPerStrip 2, Compression 5. Each strip is LZW coded by the documented
encoder in tests/test_decoders.py: strip 0 = 7 7 7 7, strip 1 = 5 6 7 8, strip 2 = 9 10.
"""
import struct

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import probe_tiff
from tests.test_decoders import lzw_encode
from tests.test_tiff_strips import SHORT, build_tiff

STRIPS = [bytes([7, 7, 7, 7]), bytes([5, 6, 7, 8]), bytes([9, 10])]
PIXELS = b"".join(STRIPS)


def tiff(strips, order=b"II"):
    o = "<" if order == b"II" else ">"
    patch = {259: (SHORT, 1, struct.pack(o + "H", 5) + b"\x00\x00")}
    return build_tiff(order, strips, 2, 5, 2, patch=patch)


def test_multi_strip_lzw_resolves_with_exact_pixels_both_orders():  # Req 12.1, 12.9
    for order in (b"II", b"MM"):
        r = Engine().run(tiff([lzw_encode(s) for s in STRIPS], order))
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == PIXELS


def test_lzw_strip_with_a_whole_extra_byte_fails_closure():  # Req 12.10
    enc = [lzw_encode(s) for s in STRIPS]
    data = tiff([enc[0], enc[1] + b"\x00", enc[2]])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_unconsumed"
    assert "range 1" in v.detail
    assert Engine().run(data).status == "FAILED"
