"""Pixel decoder: golden pixels from make_samples ground truth, synthetic depths, never-raises."""
import make_samples as ms
from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from web.pixels import FLIP_NOTE, STORED_NOTE, PixelBuffer, RenderFailure, decode


def resolve(name):
    data = corpus_bytes(name)
    result = Engine().run(data)
    assert result.status == "RESOLVED", name
    return data, result.candidate


def palette_of(data, cand):
    """Independent of the decoder: 768 bytes after the 0x0C marker at data_end."""
    if cand.trailer != "pcx_palette_256" or cand.hypothesis.bit_depth != 8:
        return None
    return data[cand.data_end + 1: cand.data_end + 769]


def run_decode(name, bottom_left=False):
    data, c = resolve(name)
    h = c.hypothesis
    return decode(c.decoded, h.width, h.height, h.bit_depth, c.row_stride, h.probe_name,
                  palette_of(data, c), bottom_left)


def grey(rows):
    return bytes(v for row in rows for v in row)


# ---- golden pixels, expected values computed from make_samples, not from the decoder ----

def test_mystery_c_bgr_becomes_rgb():
    buf = run_decode("mystery_c")
    expected = bytearray()
    for row in ms.scene(16, 16):
        for v in row:
            expected += bytes((v // 2, (v * 3) // 4, v))        # R, G, B
    assert (buf.width, buf.height, buf.channels) == (16, 16, "rgb8")
    assert buf.data == bytes(expected)
    assert STORED_NOTE in buf.note and "BGR→RGB" in buf.note


def test_mystery_h_padding_is_skipped():
    buf = run_decode("mystery_h")
    assert (buf.width, buf.height, buf.channels) == (6, 6, "grey8")
    assert buf.data == grey(ms.scene(6, 6))
    assert "no palette" in buf.note


def test_mystery_e_grey():
    buf = run_decode("mystery_e")
    assert (buf.width, buf.height) == (8, 8)
    assert buf.data == grey(ms.scene(8, 8))


def test_mystery_a_pbm_one_is_black():
    buf = run_decode("mystery_a")
    expected = bytes(0 if v < 128 else 255 for row in ms.scene(4, 4) for v in row)
    assert (buf.width, buf.height, buf.channels) == (4, 4, "grey8")
    assert buf.data == expected
    assert "1 = black" in buf.note


def test_mystery_b_and_i_use_the_pcx_palette():
    rows = ms.pcx_rle_rows()
    expected = bytearray()
    for i in rows:
        expected += bytes((i, (3 * i) % 256, 255 - i))
    for name in ("mystery_b", "mystery_i"):
        buf = run_decode(name)
        assert (buf.width, buf.height, buf.channels) == (8, 8, "rgb8"), name
        assert buf.data == bytes(expected), name
        assert "palette: pcx_palette_256" in buf.note


def test_mystery_c_descriptor_0x20_is_top_left_so_stored_order():
    data, c = resolve("mystery_c")
    d = [f for f in c.hypothesis.fields if f.name == "image_descriptor"]
    assert d and d[0].value == (0x20,)
    assert STORED_NOTE in run_decode("mystery_c").note


# ---- synthetic cases ----

def test_four_bit_odd_width_and_padded_stride():
    # width 3 at 4 bpp: 2 data bytes per row, stride 4, two padding bytes that must not be read
    rows = bytes([0x12, 0x30, 0xEE, 0xEE,  0xAB, 0xC0, 0xEE, 0xEE])
    buf = decode(rows, 3, 2, 4, 4, "generic")
    assert buf.data == bytes([17, 34, 51, 170, 187, 204])
    assert buf.channels == "grey8"


def test_one_bit_polarity_differs_for_pbm_only():
    data = bytes([0b10100000])
    other = decode(data, 3, 1, 1, 1, "generic")
    pbm = decode(data, 3, 1, 1, 1, "pbm")
    assert other.data == bytes([255, 0, 255])
    assert pbm.data == bytes([0, 255, 0])


def test_thirty_two_bit_ignores_fourth_byte_and_padding():
    # width 2, stride 12: 8 pixel bytes + 4 padding bytes
    row0 = bytes([10, 20, 30, 99,  40, 50, 60, 0]) + b"\xEE" * 4
    row1 = bytes([1, 2, 3, 255,  4, 5, 6, 7]) + b"\xEE" * 4
    buf = decode(row0 + row1, 2, 2, 32, 12, "generic")
    assert buf.data == bytes([30, 20, 10, 60, 50, 40, 3, 2, 1, 6, 5, 4])


def test_bottom_left_flips_rows_and_says_so():
    d = bytes([1, 2, 3,  4, 5, 6])          # two rows of one 24-bit pixel each
    stored = decode(d, 1, 2, 24, 3, "tga")
    flipped = decode(d, 1, 2, 24, 3, "tga", bottom_left=True)
    assert stored.data == bytes([3, 2, 1, 6, 5, 4]) and STORED_NOTE in stored.note
    assert flipped.data == bytes([6, 5, 4, 3, 2, 1]) and FLIP_NOTE in flipped.note


def test_palette_is_applied_only_when_exactly_768_bytes():
    pal = bytes(v for i in range(256) for v in (255 - i, i, (i * 7) % 256))
    idx = bytes([0, 1, 2, 255])
    ok = decode(idx, 4, 1, 8, 4, "pcx", palette=pal)
    assert ok.channels == "rgb8" and ok.data[:3] == bytes([255, 0, 0])
    assert ok.data[-3:] == bytes([0, 255, (255 * 7) % 256])
    for short in (pal[:-1], pal[:767], b"", None):
        g = decode(idx, 4, 1, 8, 4, "pcx", palette=short)
        assert g.channels == "grey8" and g.data == idx and "no palette" in g.note


def test_palette_not_applied_to_other_depths():
    pal = bytes(768)
    assert decode(bytes([0x80]), 1, 1, 1, 1, "generic", palette=pal).channels == "grey8"
    assert decode(bytes([1, 2, 3]), 1, 1, 24, 3, "generic", palette=pal).data == bytes([3, 2, 1])


def test_sixteen_bit_is_a_failure_reason():
    r = decode(bytes(8), 2, 2, 16, 4, "generic")
    assert r == RenderFailure("no renderer for 16-bit pixels")


def test_inconsistent_geometry():
    cases = [
        (bytes(10), 4, 4, 8, 4),        # too few bytes
        (bytes(16), 4, 4, 8, 3),        # stride smaller than a row
        (bytes(16), 0, 4, 8, 4),
        (bytes(16), 4, -1, 8, 4),
        (bytes(16), 4, 4, 8, 0),
    ]
    for d, w, h, bd, s in cases:
        assert decode(d, w, h, bd, s, "generic") == RenderFailure("inconsistent geometry"), (w, h, bd, s)


# ---- never raises ----

@settings(max_examples=300, deadline=None)
@given(
    decoded=st.binary(max_size=3000),
    width=st.integers(-5, 200), height=st.integers(-5, 200),
    bit_depth=st.one_of(st.sampled_from([1, 4, 8, 16, 24, 32]), st.integers(-3, 70)),
    row_stride=st.integers(-5, 800),
    probe=st.sampled_from(["pcx", "tga", "pbm", "tiff", "generic", ""]),
    palette=st.one_of(st.none(), st.binary(max_size=800), st.just(bytes(768))),
    bottom_left=st.booleans(),
)
def test_decode_never_raises_and_returns_declared_types(decoded, width, height, bit_depth,
                                                        row_stride, probe, palette, bottom_left):
    out = decode(decoded, width, height, bit_depth, row_stride, probe, palette, bottom_left)
    assert isinstance(out, (PixelBuffer, RenderFailure))
    if isinstance(out, PixelBuffer):
        per = 1 if out.channels == "grey8" else 3
        assert len(out.data) == out.width * out.height * per
        assert (out.width, out.height) == (width, height)


@settings(max_examples=50, deadline=None)
@given(decoded=st.one_of(st.none(), st.integers(), st.text(), st.binary()),
       width=st.one_of(st.none(), st.floats(), st.integers(0, 5), st.text()),
       height=st.integers(0, 5), bit_depth=st.integers(0, 40), row_stride=st.integers(0, 10))
def test_decode_tolerates_wrong_types(decoded, width, height, bit_depth, row_stride):
    out = decode(decoded, width, height, bit_depth, row_stride, "generic")
    assert isinstance(out, (PixelBuffer, RenderFailure))


# ---- PNM grey and RGB, 8 and 16 bit, scaled by maxval (Requirement 16.1) ----

def test_pnm_p5_maxval_15_scales_each_sample():
    raw = bytes([0, 1, 7, 15])                       # 2x2, v*255//15 = 17*v
    buf = decode(raw, 2, 2, 8, 2, "pnm", maxval=15)
    assert (buf.width, buf.height, buf.channels) == (2, 2, "grey8")
    assert buf.data == bytes([0, 17, 119, 255])
    assert "255//15" in buf.note


def test_pnm_p5_16bit_big_endian_maxval_65535():
    raw = bytes([0x00, 0x00, 0x12, 0x34, 0x80, 0x00, 0xFF, 0xFF])      # 4 words, 4x1
    buf = decode(raw, 4, 1, 16, 8, "pnm", maxval=65535)
    assert buf.data == bytes(v * 255 // 65535 for v in (0x0000, 0x1234, 0x8000, 0xFFFF))
    assert buf.data == bytes([0, 18, 127, 255])


def test_pnm_p5_16bit_maxval_1000_is_not_65535():
    raw = bytes([0x01, 0xF4, 0x03, 0xE8])            # 500 and 1000
    buf = decode(raw, 2, 1, 16, 4, "pnm", maxval=1000)
    assert buf.data == bytes([127, 255])


def test_pnm_p6_rgb_in_stored_order_maxval_15():
    raw = bytes([0, 5, 15, 15, 10, 0])               # two pixels, R G B stored, no BGR swap
    buf = decode(raw, 2, 1, 24, 6, "pnm", maxval=15)
    assert buf.channels == "rgb8"
    assert buf.data == bytes([0, 85, 255, 255, 170, 0])


def test_pnm_p6_48bit_big_endian_maxval_65535():
    raw = bytes([0xFF, 0xFF, 0x00, 0x00, 0x80, 0x00])        # one pixel
    buf = decode(raw, 1, 1, 48, 6, "pnm", maxval=65535)
    assert buf.channels == "rgb8" and buf.data == bytes([255, 0, 127])


def test_pnm_render_from_full_engine_run():
    header = b"P6\n2 1\n15\n"
    data = header + bytes([0, 5, 15, 15, 10, 0])
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    c = result.candidate
    h = c.hypothesis
    buf = decode(c.decoded, h.width, h.height, h.bit_depth, c.row_stride, h.probe_name, maxval=h.maxval)
    assert buf.data == bytes([0, 85, 255, 255, 170, 0])


def test_pnm_bad_maxval_or_geometry_is_a_failure_not_a_raise():
    assert decode(bytes(4), 2, 2, 8, 2, "pnm", maxval=0) == RenderFailure("inconsistent geometry")
    assert decode(bytes(3), 2, 2, 8, 2, "pnm", maxval=255) == RenderFailure("inconsistent geometry")


@settings(max_examples=100, deadline=None)
@given(decoded=st.binary(max_size=600), width=st.integers(-2, 20), height=st.integers(-2, 20),
       bit_depth=st.sampled_from([8, 16, 24, 48]), row_stride=st.integers(-2, 130),
       maxval=st.one_of(st.none(), st.integers(-5, 70000)))
def test_pnm_decode_never_raises(decoded, width, height, bit_depth, row_stride, maxval):
    out = decode(decoded, width, height, bit_depth, row_stride, "pnm", maxval=maxval)
    assert isinstance(out, (PixelBuffer, RenderFailure))
    if isinstance(out, PixelBuffer):
        assert len(out.data) == out.width * out.height * (1 if out.channels == "grey8" else 3)


# ---- plain-text PNM after a full engine run (Requirements 16.1, 16.4) ----

def _engine_pixels(data):
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    c = result.candidate
    h = c.hypothesis
    return decode(c.decoded, h.width, h.height, h.bit_depth, c.row_stride, h.probe_name, maxval=h.maxval)


def test_plain_p1_is_black_is_one_with_exact_pixels():
    # 3x2: row 0 = 1 0 1, row 1 = 0 1 0 ; 1 is black (0), 0 is white (255)
    buf = _engine_pixels(b"P1\n3 2\n1 0 1\n0 1 0\n")
    assert (buf.width, buf.height, buf.channels) == (3, 2, "grey8")
    assert buf.data == bytes([0, 255, 0, 255, 0, 255])
    assert "1 = black" in buf.note


def test_plain_p1_digit_runs_without_separators_give_the_same_pixels():
    assert _engine_pixels(b"P1\n3 2\n101010\n").data == bytes([0, 255, 0, 255, 0, 255])


def test_plain_p2_scales_by_maxval():
    buf = _engine_pixels(b"P2\n2 2\n15\n0 1\n7 15\n")
    assert buf.channels == "grey8" and buf.data == bytes([0, 17, 119, 255])


def test_plain_p3_renders_rgb_in_stored_order():
    buf = _engine_pixels(b"P3\n2 1\n15\n0 5 15 15 10 0\n")
    assert buf.channels == "rgb8" and buf.data == bytes([0, 85, 255, 255, 170, 0])


# ---- multi-plane PCX (Requirements 16.1, 16.2, 16.3, 16.5) ----

def test_pcx_three_planes_of_8_bits_are_r_g_b_per_scanline():
    # width 2, 2 rows, bytes_per_line 2: each scanline is R plane, G plane, B plane
    raw = bytes([1, 2,  3, 4,  5, 6,    7, 8,  9, 10,  11, 12])
    buf = decode(raw, 2, 2, 24, 6, "pcx", planes=3)
    assert isinstance(buf, PixelBuffer) and buf.channels == "rgb8"
    assert buf.data == bytes([1, 3, 5, 2, 4, 6,  7, 9, 11, 8, 10, 12])


def test_pcx_four_planes_of_8_bits_ignore_the_fourth_plane():
    raw = bytes([1, 2,  3, 4,  5, 6,  99, 99])          # bytes_per_line 2, one row
    buf = decode(raw, 2, 1, 32, 8, "pcx", planes=4)
    assert buf.data == bytes([1, 3, 5, 2, 4, 6]) and "fourth plane ignored" in buf.note


def test_pcx_one_bit_planes_index_the_header_palette_plane_0_lowest():
    pal = bytes(v for i in range(16) for v in (i * 16, 255 - i * 16, i))
    # width 4, 3 planes, bytes_per_line 1: pixel x has bit (7 - x) of each plane byte
    # plane0 = 1010, plane1 = 1100, plane2 = 0110 -> indices 3, 4+0... computed per pixel below
    raw = bytes([0b10100000, 0b11000000, 0b01100000])
    idx = [(p0 >> 0) | (p1 << 1) | (p2 << 2) for p0, p1, p2 in zip((1, 0, 1, 0), (1, 1, 0, 0), (0, 1, 1, 0))]
    assert idx == [3, 6, 5, 0]
    buf = decode(raw, 4, 1, 3, 3, "pcx", planes=3, header_palette=pal)
    assert buf.channels == "rgb8"
    assert buf.data == b"".join(pal[i * 3:i * 3 + 3] for i in idx)


def test_pcx_planes_with_no_renderer_name_the_layout():
    assert decode(bytes(8), 4, 1, 8, 8, "pcx", planes=2) == RenderFailure("no renderer for PCX with 2 planes of 4 bits")
    assert decode(bytes(8), 4, 1, 16, 8, "pcx", planes=2) == RenderFailure("no renderer for PCX with 2 planes of 8 bits")
    r = decode(bytes(3), 4, 1, 3, 3, "pcx", planes=3)
    assert isinstance(r, RenderFailure) and "palette" in r.reason


def test_pcx_planar_through_the_engine_and_serialiser():
    import struct
    from web.serialise import to_payload
    pal = bytes(v for i in range(16) for v in (i * 16, 255 - i * 16, i))
    header = bytearray(128)
    header[0], header[1], header[2], header[3] = 0x0A, 5, 0, 1       # manufacturer, version, no encoding, 1 bit/plane
    struct.pack_into("<4H", header, 4, 0, 0, 3, 0)                  # xmin ymin xmax ymax: 4 x 1
    header[0x10:0x40] = pal
    header[0x41] = 3                                                # planes
    struct.pack_into("<H", header, 0x42, 2)                         # bytes_per_line (even)
    data = bytes(header) + bytes([0b10100000, 0, 0b11000000, 0, 0b01100000, 0])
    out = to_payload(Engine().run(data), data, 1.0)
    render = out["candidates"][0]["render"]
    import base64
    assert base64.b64decode(render["data_b64"]) == b"".join(pal[i * 3:i * 3 + 3] for i in (3, 6, 5, 0))


@settings(max_examples=100, deadline=None)
@given(decoded=st.binary(max_size=64), width=st.integers(0, 6), height=st.integers(0, 4),
       bit_depth=st.integers(0, 40), row_stride=st.integers(0, 16), planes=st.integers(-1, 6),
       palette=st.one_of(st.none(), st.binary(max_size=60)))
def test_pcx_planar_decode_never_raises(decoded, width, height, bit_depth, row_stride, planes, palette):
    out = decode(decoded, width, height, bit_depth, row_stride, "pcx", planes=planes, header_palette=palette)
    assert isinstance(out, (PixelBuffer, RenderFailure))


# ---- TIFF 12-bit and 16-bit grey (Requirements 16.1, 16.2) ----

def _tiff_grey(order, width, height, bits, pixels, photometric=1):
    """A single-strip uncompressed grey TIFF. Header: byte order (2s at 0x00), 42 (H at 0x02), IFD offset 8 (I at 0x04).
    IFD at 8: entry count 9 (H), nine 12-byte entries (tag H, type H, count I, value at +8; SHORT = 3, LONG = 4), next
    IFD 0 (I). The strip starts at 8 + 2 + 9 * 12 + 4 = 122."""
    import struct
    o = "<" if order == b"II" else ">"
    pixel_bytes = len(pixels)
    entries = [(256, 3, width), (257, 3, height), (258, 3, bits), (259, 3, 1), (262, 3, photometric),
               (273, 4, 122), (277, 3, 1), (278, 3, height), (279, 4, pixel_bytes)]
    ifd = struct.pack(o + "H", len(entries))
    for tag, typ, val in entries:
        ifd += struct.pack(o + "HHI", tag, typ, 1) + (struct.pack(o + "H", val) + b"\0\0" if typ == 3
                                                      else struct.pack(o + "I", val))
    return order + struct.pack(o + "HI", 42, 8) + ifd + struct.pack(o + "I", 0) + pixels


def _tiff_pixels(data):
    from web.serialise import to_payload
    r = to_payload(Engine().run(data), data, 1.0)["candidates"][0]["render"]
    import base64
    return r, base64.b64decode(r["data_b64"]) if "data_b64" in r else None


def test_tiff_16bit_grey_little_and_big_endian_exact_values():
    words = [0x0000, 0x1234, 0x8000, 0xFFFF]                       # 4 x 1
    want = bytes([0, 18, 127, 255])                                # 4660 * 255 // 65535 = 18, 32768 * 255 // 65535 = 127
    for order, fmt in ((b"II", "<4H"), (b"MM", ">4H")):
        import struct
        data = _tiff_grey(order, 4, 1, 16, struct.pack(fmt, *words))
        render, raw = _tiff_pixels(data)
        assert raw == want and render["channels"] == "grey8", order
        assert "16-bit" in render["note"] and ("little" if order == b"II" else "big") in render["note"]


def test_tiff_16bit_grey_byte_order_changes_the_result():
    raw = bytes([0x12, 0x34])
    assert decode(raw, 1, 1, 16, 2, "tiff", byte_order=b"II", photometric=1).data == bytes([0x3412 * 255 // 65535])
    assert decode(raw, 1, 1, 16, 2, "tiff", byte_order=b"MM", photometric=1).data == bytes([0x1234 * 255 // 65535])
    assert isinstance(decode(raw, 1, 1, 16, 2, "tiff"), RenderFailure)       # byte order not declared


def test_tiff_12bit_grey_packs_most_significant_bit_first():
    # width 3, stride 5: samples 0xABC, 0x123, 0xFFF are bytes AB C1 23 FF F0; the last byte of a row is a half sample
    raw = bytes([0xAB, 0xC1, 0x23, 0xFF, 0xF0, 0x00, 0x10, 0x00, 0x00, 0x00])    # row 1: 0x001, 0x000, 0x000
    buf = decode(raw, 3, 2, 12, 5, "tiff", photometric=1)
    assert buf.data == bytes([0xABC * 255 // 4095, 0x123 * 255 // 4095, 255, 0, 0, 0])
    assert buf.data == bytes([171, 18, 255, 0, 0, 0])
    assert buf.channels == "grey8" and "12-bit" in buf.note


def test_tiff_12bit_grey_through_the_engine_both_byte_orders_give_the_same_pixels():
    packed = bytes([0xAB, 0xC1, 0x23, 0xFF, 0xF0])                  # width 4 would need 6 bytes; width 3 -> 5
    for order in (b"II", b"MM"):
        render, raw = _tiff_pixels(_tiff_grey(order, 3, 1, 12, packed))
        assert raw == bytes([171, 18, 255]), order


def test_tiff_photometric_zero_inverts_16bit_grey():
    buf = decode(bytes([0x00, 0x00, 0xFF, 0xFF]), 2, 1, 16, 4, "tiff", byte_order=b"MM", photometric=0)
    assert buf.data == bytes([255, 0])


def test_tiff_rgb_16_and_12_bit_have_a_named_failure():
    assert decode(bytes(12), 2, 1, 48, 12, "tiff", byte_order=b"II") == \
        RenderFailure("no renderer for 16-bit RGB TIFF (48-bit pixels)")
    assert decode(bytes(12), 2, 1, 36, 9, "tiff") == RenderFailure("no renderer for 12-bit RGB TIFF (36-bit pixels)")


@given(decoded=st.binary(max_size=64), width=st.integers(-1, 9), height=st.integers(-1, 5),
       bit_depth=st.sampled_from([12, 16, 36, 48]), row_stride=st.integers(-1, 20),
       byte_order=st.sampled_from([None, b"II", b"MM", b"XX"]), photometric=st.sampled_from([None, 0, 1, "undeclared"]))
@settings(max_examples=200, deadline=None)
def test_tiff_grey_decode_never_raises(decoded, width, height, bit_depth, row_stride, byte_order, photometric):
    out = decode(decoded, width, height, bit_depth, row_stride, "tiff", byte_order=byte_order, photometric=photometric)
    assert isinstance(out, (PixelBuffer, RenderFailure))
