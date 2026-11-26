"""Deflate TIFF through the engine (format-coverage Requirement 13, Task 25).

2 x 5 grey image, RowsPerStrip 2, Compression 8 or 32946. Each strip is a zlib stream:
strip 0 = 7 7 7 7, strip 1 = 5 6 7 8, strip 2 = 9 10.
"""
import struct
import zlib

import pytest

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import probe_tiff
from tests.test_tiff_strips import SHORT, build_tiff

STRIPS = [bytes([7, 7, 7, 7]), bytes([5, 6, 7, 8]), bytes([9, 10])]
PIXELS = b"".join(STRIPS)
ENC = [zlib.compress(s) for s in STRIPS]


def tiff(strips=ENC, order=b"II", compression=8):
    o = "<" if order == b"II" else ">"
    patch = {259: (SHORT, 1, struct.pack(o + "H", compression) + b"\x00\x00")}
    return build_tiff(order, strips, 2, 5, 2, patch=patch)


@pytest.mark.parametrize("compression", [8, 32946])
def test_multi_strip_deflate_resolves_with_exact_pixels_both_orders(compression):  # Req 13.1, 13.6
    for order in (b"II", b"MM"):
        r = Engine().run(tiff(order=order, compression=compression))
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == PIXELS


def test_deflate_strip_with_trailing_bytes_fails_closure():  # Req 13.6
    data = tiff([ENC[0], ENC[1] + b"\x00", ENC[2]])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_unconsumed"
    assert "range 1" in v.detail
    assert Engine().run(data).status == "FAILED"


def test_deflate_strip_with_corrupt_checksum_fails_closure():  # Req 13.4
    bad = bytearray(ENC[2])
    bad[-1] ^= 0xFF
    data = tiff([ENC[0], ENC[1], bytes(bad)])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_malformed"
    assert Engine().run(data).status == "FAILED"
