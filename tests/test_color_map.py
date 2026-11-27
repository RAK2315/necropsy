"""TIFF ColorMap (tag 320) as a declared field (render-fidelity Task 2.1).

Requirements 1.1 to 1.9, 7.3, 9.4. Fixtures are built in code from the layout below.

TIFF fixture (little-endian), 1650 bytes, 2 x 2 pixels, BitsPerSample 8, PhotometricInterpretation 3:
  0x00  "II" 2A 00 08 00 00 00        header: byte order, magic 42, IFD at offset 8       (<2sHI)
  0x08  08 00                         8 IFD entries                                       (<H)
  0x0A  8 entries of 12 bytes         tag H, type H, count I, value I                     (<HHII)
        256 width 2, 257 height 2, 258 bits 8, 259 compression 1, 262 photometric 3,
        273 strip offset 1646, 279 strip byte count 4, then the tag-320 entry (or an unknown tag)
  0x6A  00 00 00 00                   next IFD: none                                      (<I)
  0x6E  768 x <H                      ColorMap values, 1536 bytes
  0x66E 00 01 02 03                   pixel data, 4 bytes
"""
import struct

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.probes import _read_color_map
from tools import fc_diff

ENTRIES_AT = 0x0A
MAP_AT = 0x6E
PIXELS_AT = 0x66E
PALETTE_FILES = {"real/libtiff_palette-1c-8b.tiff", "real/goimage_video-001-paletted.tiff",
                 "real/goimage_invalid-palette-ref.tiff"}


def build_tiff(*, tag=320, type_id=3, count=768, pointer=MAP_AT, values=None, order="<"):
    """The fixture above. `tag` 65000 stands for 'the entry is not tag 320'."""
    values = values if values is not None else tuple(k * 85 % 65536 for k in range(768))
    entries = [(256, 3, 1, 2), (257, 3, 1, 2), (258, 3, 1, 8), (259, 3, 1, 1), (262, 3, 1, 3),
               (273, 4, 1, PIXELS_AT), (279, 4, 1, 4), (tag, type_id, count, pointer)]
    out = bytearray(b"II" if order == "<" else b"MM")
    out += struct.pack(order + "HI", 42, 8)
    out += struct.pack(order + "H", len(entries))
    for t, ty, c, v in entries:
        if ty == 3 and c == 1:
            out += struct.pack(order + "HHIHH", t, ty, c, v, 0)
        else:
            out += struct.pack(order + "HHII", t, ty, c, v)
    out += struct.pack(order + "I", 0)
    assert len(out) == MAP_AT
    out += struct.pack(order + "768H", *values)
    out += bytes([0, 1, 2, 3])
    return bytes(out)


def _summary(data):
    r = Engine().run(data)
    cands = [r.candidate] if r.status == "RESOLVED" else list(getattr(r, "candidates", ()))
    fields = [[(f.name, f.offset, f.fmt, f.value) for f in c.hypothesis.fields] for c in cands]
    return r, fc_diff.measure_one(data), fields


# Property 1 (Requirements 1.1 to 1.4, 1.9, 9.4)
@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=4096), st.sampled_from(["<", ">", "?", ""]), st.integers(-10, 5000),
       st.integers(-1, 70000), st.integers(-1, 2**32 + 5))
def test_read_color_map_never_raises_and_agrees_with_struct(data, order, entry, type_id, n):
    rec = _read_color_map(data, order, entry, type_id, n)
    assert rec is None or rec.name == "color_map"
    if rec is not None:
        assert type_id == 3 and 1 <= n <= 768 and rec.fmt == order + f"{n}H"
        assert rec.value == struct.unpack_from(rec.fmt, data, rec.offset)


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=4096))
def test_probe_and_engine_never_raise_on_arbitrary_bytes(data):
    Engine().run(b"II*\x00\x08\x00\x00\x00" + data)


@pytest.mark.parametrize("order", ["<", ">"])
def test_good_tag_320_is_read_as_one_field(order):
    values = tuple(range(0, 768 * 7, 7))
    data = build_tiff(values=values, order=order)
    _, _, fields = _summary(data)
    cm = [f for f in fields[0] if f[0] == "color_map"]
    assert cm == [("color_map", MAP_AT, order + "768H", values)]


# Property 2 (Requirements 1.4 to 1.8, 7.3): the Engine concludes the same with or without the record
@settings(max_examples=40, deadline=None)
@given(st.lists(st.integers(0, 65535), min_size=768, max_size=768),
       st.sampled_from([(3, 768, MAP_AT), (3, 100, MAP_AT), (4, 768, MAP_AT), (3, 0, MAP_AT),
                        (3, 769, MAP_AT), (3, 768, 60000)]))
def test_engine_result_equal_with_and_without_the_record(values, shape):
    type_id, count, pointer = shape
    with_tag = build_tiff(values=tuple(values), type_id=type_id, count=count, pointer=pointer)
    without = build_tiff(tag=65000, values=tuple(values), type_id=type_id, count=count, pointer=pointer)
    r1, key1, f1 = _summary(with_tag)
    r2, key2, f2 = _summary(without)
    assert key1 == key2
    assert (r1.status, r1.total_checks) == (r2.status, r2.total_checks)
    strip = lambda fl: [[x for x in c if x[0] != "color_map"] for c in fl]
    assert strip(f1) == f2


# Requirement 1.4: refusals record nothing and reject nothing
@pytest.mark.parametrize("kw", [dict(type_id=4), dict(count=0), dict(count=769), dict(pointer=60000)])
def test_unreadable_tag_320_records_nothing_req_1_4(kw):
    r, _, fields = _summary(build_tiff(**kw))
    assert r.status == "RESOLVED"
    assert all(f[0] != "color_map" for f in fields[0])
    assert not r.rejections


# Requirement 1.5: only the first tag 320 in directory order counts
def test_only_the_first_tag_320_entry_counts_req_1_5():
    good = build_tiff()
    # Entry 3 (the Compression entry, 0x0A + 3 * 12 = 0x2E; absent Compression means 1) becomes a bad
    # tag-320 entry: tag 320, type 4 (LONG), count 768, value MAP_AT. It comes before the good entry 7.
    bad_first = bytearray(good)
    bad_first[0x2E:0x3A] = struct.pack("<HHII", 320, 4, 768, MAP_AT)
    assert [f[0] for f in _summary(bytes(bad_first))[2][0]].count("color_map") == 0
    # The same bad entry placed after the good one (entry 3 good, entry 7 bad) records the good one once.
    good_first = bytearray(good)
    good_first[0x2E:0x3A] = struct.pack("<HHII", 320, 3, 768, MAP_AT)
    good_first[0x5E:0x6A] = struct.pack("<HHII", 320, 4, 768, MAP_AT)
    assert [f[0] for f in _summary(bytes(good_first))[2][0]].count("color_map") == 1
    assert [f[0] for f in _summary(good)[2][0]].count("color_map") == 1


# Requirements 1.6, 1.8, 1.7: corpus sweep
def test_corpus_sweep_color_map_only_on_the_three_palette_files():
    from necropsy.engine.types import hypothesis_key  # noqa: F401  (key unchanged is checked by fc_diff)
    seen = set()
    for name, path in fc_diff.sample_paths() + fc_diff.corpus_paths():
        r = Engine().run(path.read_bytes())
        cands = [r.candidate] if r.status == "RESOLVED" else list(getattr(r, "candidates", ()))
        for c in cands:
            n = sum(1 for f in c.hypothesis.fields if f.name == "color_map")
            assert n <= 1, name
            if n:
                seen.add(name)
    assert seen == PALETTE_FILES
