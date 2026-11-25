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
