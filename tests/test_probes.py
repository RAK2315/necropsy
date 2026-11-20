"""Unit tests for the four probes (requirements.md Requirement 2, 8.1, 8.2).

Expected values come from requirements.md and design.md, not from the code.
"""
import struct

import pytest

from necropsy.engine.probes import (
    PROBES,
    ProbeOutcome,
    probe_pbm,
    probe_pcx,
    probe_tga,
    probe_tiff,
    read,
)
from tests.conftest import CORPUS_NAMES, corpus_bytes


def reasons(outcome):
    return [r.reason for r in outcome.rejections]


def field(seed, name):
    return [f for f in seed.fields if f.name == name]


# --------------------------------------------------------------------- PCX
def make_pcx(encoding=0, bpp=8, xmin=0, ymin=0, xmax=7, ymax=7, bpl=8):
    """Crafted 128-byte PCX header (Req 2.5)."""
    h = bytearray(128)
    h[0x00] = 0x0A  # signature
    h[0x01] = 5  # version (unused by the probe)
    h[0x02] = encoding  # encoding declaration
    h[0x03] = bpp  # bit_depth
    struct.pack_into("<HHHH", h, 0x04, xmin, ymin, xmax, ymax)  # bounds
    h[0x41] = 1  # planes
    struct.pack_into("<H", h, 0x42, bpl)  # bytes_per_line
    return bytes(h)


def test_pcx_mystery_b_seed_is_naive_7x7_rle():
    # Req 2.5: width = xmax, height = ymax, encoding byte 0x01 -> rle_pcx
    out = probe_pcx(corpus_bytes("mystery_b"))
    s = out.seed
    assert (s.width, s.height) == (7, 7)
    assert s.encoding == "rle_pcx"
    assert s.bounds == (0, 0, 7, 7)
    assert s.header_size == 128 and s.row_alignment == 1
    assert s.probe_name == "pcx"
    assert out.rejections == ()


def test_pcx_mystery_i_encoding_none():
    # Req 2.5: byte 0x02 == 0 -> "none"
    assert probe_pcx(corpus_bytes("mystery_i")).seed.encoding == "none"


def test_pcx_mystery_h_is_5x5():
    s = probe_pcx(corpus_bytes("mystery_h")).seed
    assert (s.width, s.height) == (5, 5)


def test_pcx_encoding_byte_5_declines():
    # Req 2.10: signature 0x00 == 0x0A matches, but encoding byte 0x02 = 5 is not 0/1.
    out = probe_pcx(make_pcx(encoding=5))  # 128 bytes, byte 0x00 = 0x0A, byte 0x02 = 0x05
    assert out is not None
    assert out.seed is None
    assert len(out.rejections) == 1
    r = out.rejections[0]
    assert r.reason == "probe_precondition_failed"
    assert r.source == "pcx"
    assert r.hypothesis is None
    assert "0x02" in r.detail and "encoding" in r.detail and "0x05" in r.detail


def test_pcx_too_short_or_wrong_signature_gives_none():
    # Req 2.2, 2.10: no signature match records nothing, even with a bad encoding byte
    assert probe_pcx(make_pcx()[:127]) is None  # 127 bytes: below minimum length
    assert probe_pcx(make_pcx(encoding=5)[:127]) is None
    assert probe_pcx(b"\x00" + make_pcx()[1:]) is None  # byte 0x00 = 0x00, not 0x0A
    assert probe_pcx(b"\x00" + make_pcx(encoding=5)[1:]) is None


def test_pcx_xmax_below_xmin_seed_plus_precondition_failed():
    # Req 2.3, 2.5: precondition xmax >= xmin
    out = probe_pcx(make_pcx(xmin=5, xmax=2))
    assert out.seed.width == 2
    assert "probe_precondition_failed" in reasons(out)


# --------------------------------------------------------------------- TGA
def make_tga(id_length=0, cmt=0, itype=2, cm_len=0, cm_size=0, w=4, h=4, bpp=24):
    """Crafted 18-byte TGA header plus id field (Req 2.6)."""
    b = bytearray(18)
    b[0x00] = id_length
    b[0x01] = cmt  # colour-map type
    b[0x02] = itype  # image type
    struct.pack_into("<H", b, 0x05, cm_len)  # colour-map length
    b[0x07] = cm_size  # colour-map entry size in bits
    struct.pack_into("<HH", b, 0x0C, w, h)  # width, height
    b[0x10] = bpp
    return bytes(b) + b"\x00" * id_length


def test_tga_mystery_c():
    s = probe_tga(corpus_bytes("mystery_c")).seed
    assert (s.width, s.height, s.bit_depth, s.header_size) == (16, 16, 24, 18)
    assert s.encoding == "none" and s.row_alignment == 1


def test_tga_mystery_b_is_none():
    # mystery_b byte 0x01 == 5, not a valid colour-map type (Req 2.6)
    assert corpus_bytes("mystery_b")[0x01] == 5
    assert probe_tga(corpus_bytes("mystery_b")) is None


def test_tga_colour_mapped_header_size():
    # 18 + id_length(3) + 1 * 256 * ceil(24/8)=3 -> 789
    data = make_tga(id_length=3, cmt=1, itype=1, cm_len=256, cm_size=24, bpp=8)
    s = probe_tga(data).seed
    assert s.header_size == 18 + 3 + 1 * 256 * 3
    assert s.encoding == "none"


def test_tga_colour_map_entry_size_rounds_up():
    # 15-bit entries: ceil(15/8) = 2 -> 18 + 10 * 2
    s = probe_tga(make_tga(cmt=1, itype=1, cm_len=10, cm_size=15, bpp=8)).seed
    assert s.header_size == 38


@pytest.mark.parametrize("itype,enc", [(1, "none"), (2, "none"), (3, "none"),
                                       (9, "rle_tga"), (10, "rle_tga"), (11, "rle_tga")])
def test_tga_image_type_encoding(itype, enc):
    assert probe_tga(make_tga(itype=itype)).seed.encoding == enc


def test_tga_zero_width_precondition_failed():
    out = probe_tga(make_tga(w=0))
    assert out.seed.width == 0
    assert "probe_precondition_failed" in reasons(out)


def test_tga_mystery_c_image_descriptor_record():
    # Req 2.6, Req 7.3: image_descriptor at 0x11, format "B", value 0x20 (top-left)
    data = corpus_bytes("mystery_c")
    recs = field(probe_tga(data).seed, "image_descriptor")
    assert len(recs) == 1
    rec = recs[0]
    assert rec.offset == 0x11
    assert rec.fmt == "B"
    assert rec.value == (0x20,)
    assert struct.unpack_from("B", data, 0x11) == (0x20,)
    assert struct.unpack_from(rec.fmt, data, rec.offset) == rec.value


def _tga_with_descriptor(descriptor):
    """Crafted 18-byte TGA header, 4x4, 24 bpp, uncompressed true-colour (Req 2.6)."""
    h = bytearray(18)
    h[0x00] = 0  # id_length: no id field
    h[0x01] = 0  # color_map_type: none
    h[0x02] = 2  # image type 2: uncompressed true-colour
    # 0x03..0x07: colour-map spec, left zero
    # 0x08..0x0B: x/y origin, left zero
    struct.pack_into("<H", h, 0x0C, 4)  # width = 4
    struct.pack_into("<H", h, 0x0E, 4)  # height = 4
    h[0x10] = 24  # bit depth
    h[0x11] = descriptor  # image descriptor; bit 5 = row origin
    return bytes(h)


def test_tga_image_descriptor_reported_not_acted_on():
    # Req 2.6, Decision Record 14: bottom-left (0x00) and top-left (0x20)
    # headers yield the same seed, apart from the reported descriptor.
    bottom = probe_tga(_tga_with_descriptor(0x00)).seed
    top = probe_tga(_tga_with_descriptor(0x20)).seed
    rec = field(bottom, "image_descriptor")
    assert len(rec) == 1 and rec[0].offset == 0x11 and rec[0].fmt == "B"
    assert rec[0].value == (0x00,)
    assert field(top, "image_descriptor")[0].value == (0x20,)
    for attr in ("width", "height", "bit_depth", "header_size", "encoding"):
        assert getattr(bottom, attr) == getattr(top, attr)
    assert (bottom.width, bottom.height, bottom.bit_depth) == (4, 4, 24)
    assert (bottom.header_size, bottom.encoding) == (18, "none")


# --------------------------------------------------------------------- PBM
def test_pbm_mystery_a():
    out = probe_pbm(corpus_bytes("mystery_a"))
    s = out.seed
    assert (s.width, s.height, s.bit_depth, s.header_size) == (4, 4, 1, 7)
    assert s.encoding == "none" and s.row_alignment == 1
    magic, = field(s, "magic")
    assert (magic.offset, magic.fmt) == (0, "3s")
    width, = field(s, "width")
    assert (width.offset, width.fmt) == (3, "1s")
    height, = field(s, "height")
    assert (height.offset, height.fmt) == (5, "1s")


def test_pbm_comment_line_parses():
    # "P4\n" (0..2), "# comment\n" (3..12), "10 5\n" (13..17), data from 18
    data = b"P4\n# comment\n10 5\n" + b"\x00" * 10
    s = probe_pbm(data).seed
    assert (s.width, s.height, s.header_size) == (10, 5, 18)
    w, = field(s, "width")
    h, = field(s, "height")
    assert (w.offset, w.fmt) == (13, "2s")
    assert (h.offset, h.fmt) == (16, "1s")


def test_pbm_malformed_header_zero_seed():
    # Req 2.7: tokens are not decimal
    out = probe_pbm(b"P4\nabc def\n\x00\x00")
    s = out.seed
    assert (s.width, s.height, s.header_size) == (0, 0, 3)
    assert "probe_precondition_failed" in reasons(out)


def test_pbm_signature_mismatch_none():
    assert probe_pbm(b"P5\n4 4\n\x00") is None
    assert probe_pbm(b"P4\n") is None  # shorter than 7


# -------------------------------------------------------------------- TIFF
def make_tiff(order=b"II", entries=None, ifd_offset=8, strip_count=4, compression=1,
              bits=8, w=2, h=2):
    """Crafted single-strip TIFF (Req 2.8).

    Layout: 0..1 byte order, 2..3 magic 42, 4..7 ifd_offset, then at ifd_offset:
    2-byte entry count, 12-byte entries, 4-byte next-IFD pointer, strip data.
    Entry: tag H, type H, count I, value (SHORT: H left-justified + 2 pad; LONG: I).
    """
    o = "<" if order == b"II" else ">"
    n_entries = 7
    strip_offset = ifd_offset + 2 + 12 * n_entries + 4
    vals = entries or [
        (256, 3, w), (257, 3, h), (258, 3, bits), (259, 3, compression),
        (273, 4, strip_offset), (277, 3, 1), (279, 4, strip_count),
    ]
    buf = bytearray(order + struct.pack(o + "H", 42) + struct.pack(o + "I", ifd_offset))
    buf += struct.pack(o + "H", len(vals))
    for tag, typ, val in vals:
        if typ == 3:
            buf += struct.pack(o + "HHIH", tag, typ, 1, val) + b"\x00\x00"
        else:
            buf += struct.pack(o + "HHII", tag, typ, 1, val)
    buf += b"\x00\x00\x00\x00"  # next IFD
    buf += b"\xAA" * strip_count
    return bytes(buf), strip_offset


def test_tiff_mystery_e_big_endian():
    out = probe_tiff(corpus_bytes("mystery_e"))
    s = out.seed
    assert (s.width, s.height, s.bit_depth) == (8, 8, 8)
    assert s.header_size == 86 and s.data_end == 150
    assert s.encoding == "none"
    assert s.fields
    for f in s.fields:
        if f.fmt[-1] in "HI":  # multi-byte reads
            assert f.fmt.startswith(">"), f
    assert out.rejections == ()


def test_tiff_crafted_little_endian():
    data, strip = make_tiff(b"II")
    s = probe_tiff(data).seed
    assert (s.width, s.height, s.bit_depth) == (2, 2, 8)
    assert s.header_size == strip and s.data_end == strip + 4
    multi = [f for f in s.fields if f.fmt[-1] in "HI"]
    assert multi and all(f.fmt.startswith("<") for f in multi)
    assert field(s, "byte_order")[0].value == (b"II",)


def test_tiff_ifd_offset_past_end():
    data, _ = make_tiff(b"II")
    data = data[:8].replace(data[4:8], struct.pack("<I", 1000)) + b"\x00" * 8
    out = probe_tiff(data)
    assert out.seed is not None
    assert "field_out_of_bounds" in reasons(out)


def test_tiff_compression_5_encoding():
    data, _ = make_tiff(b"MM", compression=5)
    assert probe_tiff(data).seed.encoding == "tiff_compression_5"


def test_tiff_missing_required_tag_precondition_failed():
    # tag 279 missing
    vals = [(256, 3, 2), (257, 3, 2), (258, 3, 8), (273, 4, 100)]
    data, _ = make_tiff(b"II", entries=vals)
    assert "probe_precondition_failed" in reasons(probe_tiff(data))


def test_tiff_bad_magic_none():
    data, _ = make_tiff(b"II")
    assert probe_tiff(data[:2] + struct.pack("<H", 43) + data[4:]) is None
    assert probe_tiff(b"II*\x00") is None  # shorter than 8


# ------------------------------------------- TIFF BitsPerSample array (Req 2.8)
def tiff_raw(entries, tail=b"", order=b"II"):
    """TIFF from raw entries (tag, type, count, 4 value-field bytes).

    0..1 byte order, 2..3 magic 42, 4..7 ifd_offset 8, 8..9 entry count,
    10.. 12-byte entries, then 4 bytes next-IFD (0), then `tail` at
    10 + 12 * len(entries) + 4.
    """
    o = "<" if order == b"II" else ">"
    buf = bytearray(order + struct.pack(o + "H", 42) + struct.pack(o + "I", 8))
    buf += struct.pack(o + "H", len(entries))
    for tag, typ, count, value in entries:
        buf += struct.pack(o + "HHI", tag, typ, count) + value
    buf += b"\x00\x00\x00\x00"
    return bytes(buf + tail)


def short(v, o="<"):
    return struct.pack(o + "H", v) + b"\x00\x00"  # SHORT left-justified, 2 pad bytes


def long_(v, o="<"):
    return struct.pack(o + "I", v)


def rgb_entries(bps_entry, spp=3, planar=None):
    base = [
        (256, 3, 1, short(2)),    # width 2
        (257, 3, 1, short(2)),    # height 2
        bps_entry,
        (273, 4, 1, long_(8)),    # strip_offset 8 (value irrelevant to these tests)
        (277, 3, 1, short(spp)),  # samples_per_pixel
        (279, 4, 1, long_(12)),   # strip_byte_count 12 = 2 * 2 * 3
    ]
    if planar is not None:
        base.append((284, 3, 1, short(planar)))
    return base


def test_tiff_bps_count3_short_via_pointer():
    # 3 SHORT = 6 bytes > 4, so the value field holds an offset.
    # Entries: 6 * 12 + 2 + 4 = 78 bytes of IFD; array starts at 8 + 78 = 86.
    ptr = 8 + 2 + 12 * 6 + 4
    data = tiff_raw(rgb_entries((258, 3, 3, long_(ptr))),
                    tail=struct.pack("<3H", 8, 8, 8))  # three samples of 8 bits
    out = probe_tiff(data)
    assert out.rejections == ()
    assert out.seed.bit_depth == 24  # 8 * spp 3
    recs = field(out.seed, "bits_per_sample")
    assert [(r.offset, r.fmt, r.value) for r in recs] == [
        (ptr, "<H", (8,)), (ptr + 2, "<H", (8,)), (ptr + 4, "<H", (8,))]


def test_tiff_bps_count2_short_inline():
    # 2 SHORT = 4 bytes: values at entry+8 and entry+10 (entry 3 is at 10 + 12 * 2 = 34).
    data = tiff_raw(rgb_entries((258, 3, 2, struct.pack("<HH", 8, 8)), spp=2))
    out = probe_tiff(data)
    assert out.rejections == ()
    assert out.seed.bit_depth == 16
    recs = field(out.seed, "bits_per_sample")
    assert [(r.offset, r.fmt) for r in recs] == [(42, "<H"), (44, "<H")]


def test_tiff_bps_inline_big_endian():
    # MM order: 2 SHORT inline, values 8 and 8 big-endian.
    o = ">"  # every entry value is packed big-endian
    entries = [
        (256, 3, 1, short(2, o)), (257, 3, 1, short(2, o)),
        (258, 3, 2, struct.pack(">HH", 8, 8)),
        (273, 4, 1, long_(8, o)), (277, 3, 1, short(2, o)), (279, 4, 1, long_(12, o)),
    ]
    out = probe_tiff(tiff_raw(entries, order=b"MM"))
    assert out.rejections == ()
    assert out.seed.bit_depth == 16
    assert all(f.fmt == ">H" for f in field(out.seed, "bits_per_sample"))


def test_tiff_bps_unequal_values():
    data = tiff_raw(rgb_entries((258, 3, 2, struct.pack("<HH", 8, 16)), spp=2))
    out = probe_tiff(data)
    assert out.seed.bit_depth == 0  # nothing chosen: 0 * 2
    assert reasons(out) == ["probe_precondition_failed"]
    detail = out.rejections[0].detail
    assert "8" in detail and "16" in detail
    assert "missing tags" not in detail


def test_tiff_bps_count33_not_read():
    # 33 SHORT = 66 bytes via pointer; count alone must reject, values not read.
    ptr = 8 + 2 + 12 * 6 + 4
    data = tiff_raw(rgb_entries((258, 3, 33, long_(ptr))), tail=struct.pack("<33H", *[8] * 33))
    out = probe_tiff(data)
    assert reasons(out) == ["probe_precondition_failed"]
    assert field(out.seed, "bits_per_sample") == []
    assert out.seed.bit_depth == 0


def test_tiff_bps_count32_is_read():
    ptr = 8 + 2 + 12 * 6 + 4
    data = tiff_raw(rgb_entries((258, 3, 32, long_(ptr)), spp=1),
                    tail=struct.pack("<32H", *[1] * 32))
    out = probe_tiff(data)
    assert len(field(out.seed, "bits_per_sample")) == 32
    assert out.seed.bit_depth == 1


def test_tiff_bps_pointer_out_of_bounds():
    # Pointer 10000 is far past the end of the file (about 100 bytes).
    data = tiff_raw(rgb_entries((258, 3, 3, long_(10000))))
    out = probe_tiff(data)
    assert "field_out_of_bounds" in reasons(out)
    assert field(out.seed, "bits_per_sample") == []
    precondition = [r for r in out.rejections if r.reason == "probe_precondition_failed"]
    assert precondition and "bits_per_sample" in precondition[0].detail  # listed as missing


def test_tiff_bps_array_runs_off_end():
    # Pointer 86 is the array start but the tail holds only 2 of 3 SHORT values.
    data = tiff_raw(rgb_entries((258, 3, 3, long_(86))), tail=struct.pack("<2H", 8, 8))
    assert "field_out_of_bounds" in reasons(probe_tiff(data))


def test_tiff_planar_2_precondition_failed():
    ptr = 8 + 2 + 12 * 7 + 4  # seven entries now
    data = tiff_raw(rgb_entries((258, 3, 3, long_(ptr)), planar=2),
                    tail=struct.pack("<3H", 8, 8, 8))
    out = probe_tiff(data)
    assert reasons(out) == ["probe_precondition_failed"]
    assert "planar_configuration 2" in out.rejections[0].detail


def test_tiff_planar_1_accepted():
    ptr = 8 + 2 + 12 * 7 + 4
    data = tiff_raw(rgb_entries((258, 3, 3, long_(ptr)), planar=1),
                    tail=struct.pack("<3H", 8, 8, 8))
    assert probe_tiff(data).rejections == ()


def test_tiff_samples_per_pixel_3_with_bps_8_not_rejected():
    out = probe_tiff(tiff_raw(rgb_entries((258, 3, 1, short(8)), spp=3)))
    assert out.rejections == ()
    assert out.seed.bit_depth == 24


def test_tiff_bps_records_round_trip():
    ptr = 8 + 2 + 12 * 6 + 4
    inputs = [
        tiff_raw(rgb_entries((258, 3, 3, long_(ptr))), tail=struct.pack("<3H", 8, 8, 8)),
        tiff_raw(rgb_entries((258, 3, 2, struct.pack("<HH", 8, 16)), spp=2)),
        tiff_raw(rgb_entries((258, 4, 3, long_(ptr))), tail=struct.pack("<3I", 8, 8, 8)),
    ]
    for data in inputs:
        out = probe_tiff(data)
        for hyp in [out.seed] + [r.hypothesis for r in out.rejections if r.hypothesis]:
            for f in hyp.fields:
                assert struct.unpack_from(f.fmt, data, f.offset) == f.value


# Requirement 7.13: width, height, bit_depth, data region (header_size is 8).
REAL_TIFFS = [
    ("goimage_no_compress.tiff", 16, 15, 32, 968),
    ("goimage_no_rps.tiff", 16, 15, 32, 968),
    ("goimage_video-001-uncompressed.tiff", 150, 103, 24, 46358),
    ("sdlimage_sample.tif", 23, 42, 24, 2906),
]


@pytest.mark.parametrize("name,w,h,depth,end", REAL_TIFFS)
def test_tiff_real_files_seed_without_rejection(name, w, h, depth, end):
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "spike" / "samples" / "real" / name
    data = path.read_bytes()
    out = probe_tiff(data)
    assert out.rejections == ()
    s = out.seed
    assert (s.width, s.height, s.bit_depth) == (w, h, depth)
    assert (s.header_size, s.data_end) == (8, end)
    for f in s.fields:
        assert struct.unpack_from(f.fmt, data, f.offset) == f.value


# ------------------------------------------------------- order, round trips
def test_probes_order_is_pcx_tga_pbm_tiff():
    # Req 2.1
    assert [name for name, _ in PROBES] == ["pcx", "tga", "pbm", "tiff"]
    assert [fn for _, fn in PROBES] == [probe_pcx, probe_tga, probe_pbm, probe_tiff]


def crafted_inputs():
    return [
        make_pcx(), make_pcx(xmin=5, xmax=2),
        make_tga(), make_tga(id_length=3, cmt=1, itype=1, cm_len=256, cm_size=24, bpp=8),
        b"P4\n# comment\n10 5\n" + b"\x00" * 10, b"P4\nabc def\n\x00\x00",
        make_tiff(b"II")[0], make_tiff(b"MM", compression=5)[0],
    ]


def test_every_field_record_round_trips():
    # Req 8.2: struct.unpack_from(fmt, data, offset) == value
    inputs = [corpus_bytes(n) for n in CORPUS_NAMES] + crafted_inputs()
    checked = 0
    for data in inputs:
        for _, probe in PROBES:
            out = probe(data)
            if out is None:
                continue
            assert isinstance(out, ProbeOutcome)
            hyps = [out.seed] + [r.hypothesis for r in out.rejections if r.hypothesis]
            for hyp in hyps:
                for f in hyp.fields:
                    assert struct.unpack_from(f.fmt, data, f.offset) == f.value
                    checked += 1
    assert checked > 0


def test_read_helper_bounds():
    data = b"\x01\x02\x03"
    assert read(data, "x", 1, "<H").value == (0x0302,)
    assert read(data, "x", 2, "<H") is None
    assert read(data, "x", -1, "B") is None


# ------------------------------------------------- never-raises properties
# Feature: structure-inference-engine, Probe never raises
# Validates: Requirements 2.3, 6.4, 6.7
from hypothesis import given, settings, strategies as st

from necropsy.engine.types import REASONS, Hypothesis

PROBE_FNS = {"pcx": probe_pcx, "tga": probe_tga, "pbm": probe_pbm, "tiff": probe_tiff}
MIN_LEN = {"pcx": 128, "tga": 18, "pbm": 7, "tiff": 8}

_tail = st.binary(max_size=4096)


def _pad(prefix_and_tail, n):
    return prefix_and_tail.ljust(n, b"\x00")


# Signature-prefixed generators (Req 2.5 to 2.8), padded to the probe's minimum length.
SIGNED = {
    "pcx": st.builds(
        lambda a, e, t: _pad(bytes([0x0A, a, e]) + t, 128),
        st.integers(0, 255), st.sampled_from([0, 1]), _tail),
    "tga": st.builds(
        lambda i, c, t, rest: _pad(bytes([i, c, t]) + rest, 18),
        st.integers(0, 255), st.sampled_from([0, 1]),
        st.sampled_from([1, 2, 3, 9, 10, 11]), _tail),
    "pbm": st.builds(lambda t: _pad(b"P4\n" + t, 7), _tail),
    "tiff": st.builds(lambda m, t: _pad(m + t, 8),
                      st.sampled_from([b"II*\x00", b"MM\x00*"]), _tail),
}


def check_outcome(data, out):
    assert out is None or isinstance(out, ProbeOutcome)
    if out is None:
        return
    if out.seed is None:
        # Requirements 2.3 / 2.10: a probe may only decline, with exactly one
        # probe_precondition_failed rejection that carries no hypothesis.
        assert len(out.rejections) == 1
        assert out.rejections[0].reason == "probe_precondition_failed"
        assert out.rejections[0].hypothesis is None
        return
    assert isinstance(out.seed, Hypothesis)
    for r in out.rejections:
        assert r.reason in REASONS
    hyps = [out.seed] + [r.hypothesis for r in out.rejections if r.hypothesis]
    for hyp in hyps:
        for f in hyp.fields:  # Req 8.2
            assert struct.unpack_from(f.fmt, data, f.offset) == f.value


def _arbitrary(name):
    probe = PROBE_FNS[name]

    @settings(max_examples=100, deadline=None)
    @given(st.binary(max_size=65536))
    def prop(data):
        check_outcome(data, probe(data))

    return prop


def _signed(name):
    probe = PROBE_FNS[name]

    @settings(max_examples=100, deadline=None)
    @given(SIGNED[name])
    def prop(data):
        out = probe(data)
        check_outcome(data, out)
        if len(data) >= MIN_LEN[name]:
            assert out is not None  # Req 2.3: signature match always emits a seed

    return prop


test_pcx_never_raises_arbitrary = _arbitrary("pcx")
test_tga_never_raises_arbitrary = _arbitrary("tga")
test_pbm_never_raises_arbitrary = _arbitrary("pbm")
test_tiff_never_raises_arbitrary = _arbitrary("tiff")
test_pcx_never_raises_signed = _signed("pcx")
test_tga_never_raises_signed = _signed("tga")
test_pbm_never_raises_signed = _signed("pbm")
test_tiff_never_raises_signed = _signed("tiff")