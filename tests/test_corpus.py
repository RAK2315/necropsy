"""Corpus tests: exact outcomes for the nine sample files (Requirement 7).

Expected values come from requirements.md Requirement 7 and design.md
"Corpus Trace (measured)", not from the engine.
"""
import struct

import pytest

import make_samples
from necropsy.engine import Engine
from tests.conftest import CORPUS_NAMES, corpus_bytes

RESOLVED_NAMES = ("mystery_a", "mystery_b", "mystery_c", "mystery_e", "mystery_h", "mystery_i")


def run(name):
    return Engine().run(corpus_bytes(name))


def key_of(c):
    h = c.hypothesis
    return (h.width, h.height, h.bit_depth, h.header_size, h.row_alignment, h.encoding, h.data_end)


def check_resolved(name, stage, probe, w, h, bpp, header, align, stride, enc, region, trailer, path):
    r = run(name)
    assert r.status == "RESOLVED"
    assert r.stage == stage
    c = r.candidate
    hy = c.hypothesis
    assert hy.probe_name == probe
    assert (hy.width, hy.height, hy.bit_depth, hy.header_size) == (w, h, bpp, header)
    assert hy.row_alignment == align
    assert c.row_stride == stride
    assert hy.encoding == enc
    assert (c.data_start, c.data_end) == region
    assert c.trailer == trailer
    assert tuple(hy.revision_path) == path
    return r


def test_mystery_a():
    check_resolved("mystery_a", "probe", "pbm", 4, 4, 1, 7, 1, 1, "none", (7, 11), None, ())


def test_mystery_b():
    r = check_resolved("mystery_b", "revision", "pcx", 8, 8, 8, 128, 1, 8, "rle_pcx",
                       (128, 186), "pcx_palette_256", ("inclusive_bounds",))
    hits = [e for e in r.rejections
            if e.reason == "decoder_unconsumed" and e.source == "pcx"
            and e.hypothesis is not None
            and (e.hypothesis.width, e.hypothesis.height) == (7, 7)
            and e.hypothesis.encoding == "rle_pcx" and e.hypothesis.header_size == 128]
    assert hits


def test_mystery_c():
    r = check_resolved("mystery_c", "probe", "tga", 16, 16, 24, 18, 1, 48, "none", (18, 786), None, ())
    # Requirement 7.3: image_descriptor at 0x11, format "B", value 0x20 (top-left origin).
    descs = [f for f in r.candidate.hypothesis.fields if f.name == "image_descriptor"]
    assert len(descs) == 1
    fr = descs[0]
    assert fr.offset == 0x11
    assert fr.fmt == "B"
    assert fr.value == (0x20,)
    assert struct.unpack_from("B", corpus_bytes("mystery_c"), 0x11) == (0x20,)


def test_mystery_e():
    r = check_resolved("mystery_e", "probe", "tiff", 8, 8, 8, 86, 1, 8, "none", (86, 150), None, ())
    multi = [f for f in r.candidate.hypothesis.fields
             if f.fmt.lstrip("<>=!@")[:1].isdigit() is False
             and any(ch in f.fmt for ch in "HIiLlQq")]
    assert multi
    assert all(f.fmt.startswith(">") for f in multi)


def _ambiguous(name, true_key):
    r = run(name)
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "generic"
    keys = [key_of(c) for c in r.candidates]
    assert true_key in keys
    return r


def test_mystery_d():
    _ambiguous("mystery_d", (8, 8, 8, 40, 1, "none", None))


def test_mystery_f():
    r = _ambiguous("mystery_f", (12, 10, 8, 12, 1, "none", None))
    cand = next(c for c in r.candidates if key_of(c) == (12, 10, 8, 12, 1, "none", None))
    fmts = {f.fmt for f in cand.hypothesis.fields
            if f.name == "width" and f.offset == 0 and f.value[0] == 12}
    assert len(fmts & {"<H", "<I", "<i"}) >= 2


def test_mystery_g():
    _ambiguous("mystery_g", (8, 8, 24, 20, 1, "none", None))


def test_mystery_h():
    r = check_resolved("mystery_h", "revision", "pcx", 6, 6, 8, 128, 4, 8, "none",
                       (128, 176), None, ("inclusive_bounds", "row_padding_variants"))
    assert ("row_padding_variants", "inclusive_bounds") in [
        tuple(p) for p in r.candidate.alternative_paths]


def test_mystery_i():
    r = check_resolved("mystery_i", "revision", "pcx", 8, 8, 8, 128, 1, 8, "rle_pcx",
                       (128, 186), "pcx_palette_256", ("inclusive_bounds", "rle_pcx"))
    assert ("rle_pcx", "inclusive_bounds") in [tuple(p) for p in r.candidate.alternative_paths]


@pytest.mark.parametrize("name", RESOLVED_NAMES)
def test_resolved_pixels_exact(name):
    r = run(name)
    assert r.status == "RESOLVED"
    assert r.candidate.decoded == make_samples.pixels(name)


@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_no_corpus_file_fails(name):
    assert run(name).status != "FAILED"


# --- external_b: Pillow TGA 2.0 with footer (Requirement 7.12) -------------------
def _read_ppm(path):
    """Parse a binary P6 PPM; return (width, height, pixel bytes in RGB order)."""
    raw = path.read_bytes()
    pos = 0
    tokens = []
    while len(tokens) < 4:
        while raw[pos:pos + 1].isspace():
            pos += 1
        if raw[pos:pos + 1] == b"#":
            while raw[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while not raw[pos:pos + 1].isspace():
            pos += 1
        tokens.append(raw[start:pos])
    pos += 1  # exactly one whitespace byte after maxval
    assert tokens[0] == b"P6" and tokens[3] == b"255"
    w, h = int(tokens[1]), int(tokens[2])
    pixels = raw[pos:]
    assert len(pixels) == w * h * 3
    return w, h, pixels


def test_external_b_resolves_with_tga2_footer_req_7_12():
    from tests.conftest import SAMPLES_DIR
    data = (SAMPLES_DIR / "external" / "external_b").read_bytes()
    assert len(data) == 9260
    r = Engine().run(data)
    assert r.status == "RESOLVED"
    assert r.stage == "probe"
    c = r.candidate
    hy = c.hypothesis
    assert hy.probe_name == "tga"
    assert (hy.width, hy.height, hy.bit_depth, hy.header_size) == (64, 48, 24, 18)
    assert tuple(hy.revision_path) == ()
    assert c.trailer == "tga2_footer"
    assert (c.data_start, c.data_end) == (18, 9234)
    descs = [f for f in hy.fields if f.name == "image_descriptor"]
    assert len(descs) == 1 and descs[0].value == (0x00,)
    # Source pixels stored bottom row first, each pixel as B, G, R.
    w, h, rgb = _read_ppm(SAMPLES_DIR / "external" / "source.ppm")
    assert (w, h) == (64, 48)
    expected = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            i = (y * w + x) * 3
            expected += bytes((rgb[i + 2], rgb[i + 1], rgb[i]))
    assert bytes(c.decoded) == bytes(expected)


# --- real files: pillow_p_16.tga and pillow_rgb32rle.tga (Requirements 7.16, 7.17) ---
def test_pillow_p_16_tga_resolves_req_7_16():
    from tests.conftest import SAMPLES_DIR
    path = SAMPLES_DIR / "real" / "pillow_p_16.tga"
    data = path.read_bytes()
    r = Engine().run(data)
    assert r.status == "RESOLVED"
    assert r.stage == "probe"
    c = r.candidate
    hy = c.hypothesis
    assert hy.probe_name == "tga"
    assert (hy.width, hy.height, hy.bit_depth, hy.header_size) == (128, 128, 8, 560)
    assert (c.data_start, c.data_end) == (560, 16944)
    assert c.data_end - c.data_start == 16384
    assert c.trailer == "tga2_footer"
    # Pillow is imported only here; for a palette image its raw bytes are the pixel indices.
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        expected = im.tobytes()
    assert len(expected) == 16384
    assert bytes(c.decoded) == expected


def test_pillow_rgb32rle_tga_not_resolved_req_7_17():
    from tests.conftest import SAMPLES_DIR
    data = (SAMPLES_DIR / "real" / "pillow_rgb32rle.tga").read_bytes()
    r = Engine().run(data)
    assert r.status != "RESOLVED"
    tga = [e for e in r.rejections
           if e.source == "tga" and e.hypothesis is not None and e.hypothesis.probe_name == "tga"]
    assert tga, "the TGA seed must appear among the rejections"
    assert all(e.reason == "unsupported_encoding" for e in tga)
