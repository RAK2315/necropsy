"""LZMA TIFF through the engine (format-coverage Requirement 14, Task 26).

2 x 5 grey image, RowsPerStrip 2, Compression 34925. Each strip is an xz stream:
strip 0 = 7 7 7 7, strip 1 = 5 6 7 8, strip 2 = 9 10.
"""
import lzma
import struct

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import probe_tiff
from tests.test_tiff_strips import SHORT, build_tiff

STRIPS = [bytes([7, 7, 7, 7]), bytes([5, 6, 7, 8]), bytes([9, 10])]
PIXELS = b"".join(STRIPS)
ENC = [lzma.compress(s) for s in STRIPS]


def tiff(strips=ENC, order=b"II"):
    o = "<" if order == b"II" else ">"
    patch = {259: (SHORT, 1, struct.pack(o + "H", 34925) + b"\x00\x00")}
    return build_tiff(order, strips, 2, 5, 2, patch=patch)


def test_multi_strip_lzma_resolves_with_exact_pixels_both_orders():  # Req 14.1, 14.3
    for order in (b"II", b"MM"):
        r = Engine().run(tiff(order=order))
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == PIXELS


def test_lzma_strip_with_trailing_bytes_fails_closure():  # Req 14.3
    data = tiff([ENC[0], ENC[1] + b"\x00", ENC[2]])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_unconsumed"
    assert Engine().run(data).status == "FAILED"


def test_lzma_corrupt_strip_fails_closure():  # Req 14.3
    data = tiff([ENC[0], ENC[1], b"\xfd7zXZ\x00" + b"\xff" * 30])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_malformed"
    assert Engine().run(data).status == "FAILED"
