"""PackBits TIFF through the engine (format-coverage Requirement 11, Task 23).

2 x 5 grey image, RowsPerStrip 2, Compression 32773. Strip bytes are PackBits packets:
  strip 0 rows 0-1 (4 px): FD 07            run of 4 x 07
  strip 1 rows 2-3 (4 px): 03 05 06 07 08   literal of 4
  strip 2 row 4    (2 px): 80 01 09 0A      no-op, then literal of 2
"""
import struct

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import probe_tiff
from tests.test_tiff_strips import SHORT, build_tiff

ENC = [b"\xfd\x07", b"\x03\x05\x06\x07\x08", b"\x80\x01\x09\x0a"]
PIXELS = bytes([7, 7, 7, 7, 5, 6, 7, 8, 9, 10])


def tiff(strips=ENC, order=b"II"):
    o = "<" if order == b"II" else ">"
    patch = {259: (SHORT, 1, struct.pack(o + "H", 32773) + b"\x00\x00")}
    return build_tiff(order, strips, 2, 5, 2, patch=patch)


def test_multi_strip_packbits_resolves_with_exact_pixels_both_orders():
    for order in (b"II", b"MM"):
        r = Engine().run(tiff(order=order))
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == PIXELS


def test_padded_strip_fails_closure_naming_the_range():  # Req 11.7
    data = tiff([ENC[0], ENC[1] + b"\x00\x00", ENC[2]])
    seed = probe_tiff(data).seed
    v = check_closure(seed, data)
    assert not v.ok and v.reason == "decoder_unconsumed"
    assert "range 1" in v.detail
    assert Engine().run(data).status == "FAILED"


def test_trailing_0x80_in_a_strip_fails_closure():  # Req 11.6
    data = tiff([ENC[0], ENC[1], ENC[2] + b"\x80"])
    v = check_closure(probe_tiff(data).seed, data)
    assert not v.ok and v.reason == "decoder_unconsumed"
