"""Trailer readings (Requirement 1.17, 4.10, 7.19, 7.20; Decision Record item 24).

Every input is built in code from the byte layouts stated in the comments.
Expected values come from the requirements, not from running the engine.
"""
from __future__ import annotations

import struct

import pytest

import necropsy.engine.engine as engine_mod
from necropsy.engine import Engine
from necropsy.engine.budget import Budget as RealBudget


# ---- Requirement 7.19: crafted headerless 1,036-byte file -------------------
# Bytes 0..12: struct.pack('<III', 32, 32, 8). Bytes 12..1036: 32x32 pixels,
# pixel(x, y) = (x*7 + y*3) % 200 + 20, row-major. Byte 267 = 1036 - 769 is 0x0C.
def crafted_1036(with_marker: bool) -> bytes:
    pixels = bytes((x * 7 + y * 3) % 200 + 20 for y in range(32) for x in range(32))
    data = bytearray(struct.pack("<III", 32, 32, 8) + pixels)
    assert len(data) == 1036
    if with_marker:
        data[267] = 0x0C
    return bytes(data)


EXPECTED_SHAPES = {(32, 8, 32), (32, 32, 8), (8, 32, 32)}


def _shapes(result):
    return [(c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth)
            for c in result.candidates]


def test_req_7_19_crafted_file_with_marker_is_three_way_ambiguity():
    r = Engine().run(crafted_1036(True))
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "generic"
    assert len(r.candidates) == 3
    assert set(_shapes(r)) == EXPECTED_SHAPES
    for c in r.candidates:
        assert c.hypothesis.header_size == 12
        assert (c.data_start, c.data_end) == (12, 1036)
        assert c.trailer is None


def test_req_7_19_crafted_file_without_marker_is_same_three_with_3_checks():
    r = Engine().run(crafted_1036(False))
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "generic"
    assert set(_shapes(r)) == EXPECTED_SHAPES and len(r.candidates) == 3
    assert r.total_checks == 3
    for c in r.candidates:
        assert (c.hypothesis.header_size, c.data_start, c.data_end, c.trailer) == (12, 12, 1036, None)


# ---- Probe path: PCX ---------------------------------------------------------
# PCX header, 128 bytes: byte 0 = 0x0A, byte 1 version = 5, byte 2 encoding = 0,
# byte 3 bit depth = 8, <HHHH xmin ymin xmax ymax at 4 = 0, 0, 40, 40,
# byte 0x41 planes = 1, <H bytes_per_line at 0x42 = 40. Then 1,600 data bytes
# (pixel (x, y) = (x*7+y*3) % 150 + 20). Byte 1600 - 769 = 831 of the data is 0x0C, so
# the palette trailer matches: the trailer reading is [128, 959) (831 bytes) and
# the end-of-file reading is [128, 1728) (1,600 bytes = 40 x 40 x 8 bit).
def _pcx_header(xmax: int, ymax: int) -> bytes:
    h = bytearray(128)
    h[0], h[1], h[2], h[3] = 0x0A, 5, 0, 8
    struct.pack_into("<HHHH", h, 4, 0, 0, xmax, ymax)
    h[0x41] = 1
    struct.pack_into("<H", h, 0x42, 40)
    return bytes(h)


def _pcx_body() -> bytearray:
    body = bytearray((x * 7 + y * 3) % 150 + 20 for y in range(40) for x in range(40))
    body[1600 - 769] = 0x0C
    return body


PCX_PROBE = _pcx_header(40, 40) + bytes(_pcx_body())        # seed 40x40 closes at end of file
PCX_REVISION = _pcx_header(39, 39) + bytes(_pcx_body())     # seed 39x39; inclusive bounds gives 40x40


def test_probe_path_end_of_file_reading_resolves_after_trailer_reading_fails():
    r = Engine().run(PCX_PROBE)
    assert r.status == "RESOLVED"
    assert r.stage == "probe"
    c = r.candidate
    assert (c.data_start, c.data_end) == (128, len(PCX_PROBE))
    assert c.trailer is None
    assert c.decoded == PCX_PROBE[128:]
    failed = [e for e in r.rejections
              if e.source == "pcx" and e.hypothesis is not None and e.hypothesis.data_end is None]
    assert [(e.reason, e.discrepancy) for e in failed] == [("arithmetic_mismatch", 831 - 1600)]


def test_probe_path_both_readings_are_charged():
    r = Engine().run(PCX_PROBE)
    assert r.total_checks == 2


def test_cap_of_one_on_probe_path_input_gives_search_cap_exceeded(monkeypatch):
    def capped(deadline_seconds, cap=10_000, clock=None, **kw):
        args = {"clock": clock} if clock is not None else {}
        return RealBudget(deadline_seconds, cap=1, **args)

    monkeypatch.setattr(engine_mod, "Budget", capped)
    r = Engine().run(PCX_PROBE)
    assert r.status == "FAILED"
    assert r.termination == "search_cap_exceeded"
    assert r.total_checks == 1


def test_cap_of_three_on_probe_path_input_still_checks_both_readings(monkeypatch):
    def capped(deadline_seconds, cap=10_000, clock=None, **kw):
        args = {"clock": clock} if clock is not None else {}
        return RealBudget(deadline_seconds, cap=3, **args)

    monkeypatch.setattr(engine_mod, "Budget", capped)
    r = Engine().run(PCX_PROBE)
    assert r.status == "RESOLVED"
    assert r.total_checks == 2


def test_engine_closure_checks_both_readings_of_the_seed(monkeypatch):
    seen = []
    real = engine_mod.check_closure

    def spy(h, data):
        seen.append(h.data_end)
        return real(h, data)

    monkeypatch.setattr(engine_mod, "check_closure", spy)
    Engine().run(PCX_PROBE)
    assert seen[:2] == [None, len(PCX_PROBE)]


# ---- Revision path -----------------------------------------------------------
def test_revision_path_end_of_file_reading_closes_only_after_a_strategy():
    r = Engine().run(PCX_REVISION)
    assert r.status == "RESOLVED"
    assert r.stage == "revision"
    c = r.candidate
    assert c.hypothesis.revision_path == ("inclusive_bounds",)
    assert (c.hypothesis.width, c.hypothesis.height) == (40, 40)
    assert (c.data_start, c.data_end, c.trailer) == (128, len(PCX_REVISION), None)
    trailer_child = [e for e in r.rejections
                     if e.source == "revision:inclusive_bounds"
                     and e.hypothesis is not None and e.hypothesis.data_end is None
                     and (e.hypothesis.width, e.hypothesis.height) == (40, 40)]
    assert [e.reason for e in trailer_child] == ["arithmetic_mismatch"]


# ---- Both readings close: trailer reading first --------------------------------
# Header 16 bytes: struct.pack('<IIII', 1, 100, 869, 8). Data region of the
# trailer reading: 100 zero bytes [16, 116) = 1 x 100 at 8 bit. Then a 769-byte
# palette trailer: 0x0C then 768 zeros. File length 885, so the end-of-file reading
# is [16, 885) = 869 bytes = 1 x 869 at 8 bit.
def test_both_readings_closing_is_ambiguity_with_trailer_reading_first():
    data = struct.pack("<IIII", 1, 100, 869, 8) + bytes(100) + b"\x0c" + bytes(768)
    assert len(data) == 885
    r = Engine().run(data)
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "generic"
    at16 = [c for c in r.candidates if c.hypothesis.header_size == 16]
    trailer_ones = [i for i, c in enumerate(at16) if c.hypothesis.data_end is None]
    eof_ones = [i for i, c in enumerate(at16) if c.hypothesis.data_end == 885]
    assert trailer_ones and eof_ones
    assert max(trailer_ones) < min(eof_ones)
    assert any((c.hypothesis.width, c.hypothesis.height, c.trailer, c.data_end)
               == (1, 100, "pcx_palette_256", 116) for c in at16)
    assert any((c.hypothesis.width, c.hypothesis.height, c.trailer, c.data_end)
               == (1, 869, None, 885) for c in at16)


# ---- field_out_of_bounds trailer reading leaves the end-of-file reading checked ---
# TGA header 18 bytes (<BBB HHB HHHH BB): id 0, colour-map type 0, image type 3,
# colour-map spec zeros, origin 0, 0, width 9, height 10, 8 bit, descriptor 0.
# Then 64 pixel bytes and a 26-byte footer: extension_area_offset <I = 5000 (outside
# [18, 82)), developer_area_offset <I = 0, "TRUEVISION-XFILE.\0". The end-of-file
# reading is [18, 108) = 90 bytes = 9 x 10 at 8 bit.
_SIG = b"TRUEVISION-XFILE.\x00"


def _tga_bad_footer() -> bytes:
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 3, 0, 0, 0, 0, 0, 9, 10, 8, 0)
    assert len(header) == 18
    pixels = bytes((x * 7 + y * 3) % 200 + 20 for y in range(8) for x in range(8))
    return header + pixels + struct.pack("<II", 5000, 0) + _SIG


def test_probe_path_field_out_of_bounds_trailer_reading_leaves_eof_reading():
    data = _tga_bad_footer()
    assert len(data) == 108
    r = Engine().run(data)
    assert r.status == "RESOLVED" and r.stage == "probe"
    assert (r.candidate.data_start, r.candidate.data_end, r.candidate.trailer) == (18, 108, None)
    assert [e.reason for e in r.rejections
            if e.source == "tga" and e.hypothesis is not None and e.hypothesis.data_end is None
            ] == ["field_out_of_bounds"]


# Headerless: struct.pack('<III', 10, 9, 8) + 64 pixel bytes + the same bad footer.
# The end-of-file reading is [12, 102) = 90 bytes = 10 x 9 at 8 bit.
def test_generic_field_out_of_bounds_trailer_reading_leaves_eof_reading():
    pixels = bytes((x * 7 + y * 3) % 200 + 20 for y in range(8) for x in range(8))
    data = struct.pack("<III", 10, 9, 8) + pixels + struct.pack("<II", 5000, 0) + _SIG
    assert len(data) == 102
    r = Engine().run(data)
    assert r.status in ("RESOLVED", "UNRESOLVED_AMBIGUITY")
    cands = [r.candidate] if r.status == "RESOLVED" else list(r.candidates)
    assert any((c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth,
                c.hypothesis.header_size, c.data_start, c.data_end, c.trailer)
               == (10, 9, 8, 12, 12, 102, None) for c in cands)
    assert any(e.reason == "field_out_of_bounds" and e.source == "generic" and e.hypothesis is None
               for e in r.rejections)
