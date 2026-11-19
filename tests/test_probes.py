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


def test_pcx_encoding_byte_2_gives_none():
    # Req 2.5 signature: byte 0x02 must be 0 or 1
    data = bytearray(corpus_bytes("mystery_b"))
    data[0x02] = 2
    assert probe_pcx(bytes(data)) is None


def test_pcx_too_short_or_wrong_signature_gives_none():
    # Req 2.2
    assert probe_pcx(make_pcx()[:127]) is None
    assert probe_pcx(b"\x00" + make_pcx()[1:]) is None


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
