"""render-fidelity task 3.1: the renderer refuses sub-byte multi-channel TIFF (Requirements 6, 7.1, 7.2, 9.3).

The Requirement 6 fixture is built in code from the 118-byte table in the design ("Fixture layout for Requirement 6").
It is not copied from, derived from or compared with any other file. Expectations come from the table, not from decode.
"""
import json
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from tools import fc_diff
from web.pixels import PixelBuffer, RenderFailure, SUBBYTE_REASON, decode
from web.serialise import to_payload

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "data" / "render_fidelity_golden_decode.json"


def _le_entry(tag: int, type_id: int, count: int, value: int) -> bytes:
    """One 12-byte little-endian IFD entry: tag (H), type (H), count (I), value field (I, 4 bytes)."""
    return (tag.to_bytes(2, "little") + type_id.to_bytes(2, "little")
            + count.to_bytes(4, "little") + value.to_bytes(4, "little"))


def build_subbyte_fixture() -> bytes:
    """A 2 x 2 little-endian TIFF of 4 samples of 4 bits each (bit depth 16, row 4 bytes), 118 bytes."""
    parts = [
        b"\x49\x49",              # 0x00 byte order "II": little-endian
        b"\x2A\x00",              # 0x02 magic 42
        b"\x08\x00\x00\x00",      # 0x04 IFD at offset 8
        b"\x08\x00",              # 0x08 8 IFD entries
        _le_entry(256, 3, 1, 2),      # 0x0A tag 256 ImageWidth, SHORT, count 1, value 2 (+2 pad bytes)
        _le_entry(257, 3, 1, 2),      # 0x16 tag 257 ImageLength, SHORT, count 1, value 2
        _le_entry(258, 3, 1, 4),      # 0x22 tag 258 BitsPerSample, SHORT, count 1, value 4
        _le_entry(259, 3, 1, 1),      # 0x2E tag 259 Compression, SHORT, count 1, value 1 (none)
        _le_entry(262, 3, 1, 2),      # 0x3A tag 262 PhotometricInterpretation, SHORT, count 1, value 2 (RGB)
        _le_entry(273, 4, 1, 110),    # 0x46 tag 273 StripOffsets, LONG, count 1, value 110 (0x6E)
        _le_entry(277, 3, 1, 4),      # 0x52 tag 277 SamplesPerPixel, SHORT, count 1, value 4
        _le_entry(279, 4, 1, 8),      # 0x5E tag 279 StripByteCount, LONG, count 1, value 8
        b"\x00\x00\x00\x00",      # 0x6A offset of the next IFD: 0, none
        bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0]),   # 0x6E pixel data: 2 rows of 4 bytes
    ]
    return b"".join(parts)


FIXTURE_REASON = "no renderer for TIFF with 4 samples per pixel of 4 bits each"


def _outcome(r):
    if isinstance(r, PixelBuffer):
        return ["P", r.width, r.height, r.channels, r.data.hex(), r.note]
    return ["F", r.reason]


def test_fixture_matches_the_table():
    data = build_subbyte_fixture()
    assert len(data) == 0x76 == 118
    assert data[0x00:0x04] == bytes.fromhex("49492A00")
    assert data[0x0A:0x16] == bytes.fromhex("000103000100000002000000")    # ImageWidth 2
    assert data[0x22:0x2E] == bytes.fromhex("020103000100000004000000")    # BitsPerSample 4
    assert data[0x46:0x52] == bytes.fromhex("11010400010000006E000000")
    assert data[0x5E:0x6A] == bytes.fromhex("170104000100000008000000")    # StripByteCount 8
    assert data[0x6E:] == bytes.fromhex("123456789ABCDEF0")


def test_pinned_string():
    assert SUBBYTE_REASON.format(spp=4, bps=4) == FIXTURE_REASON


def test_fixture_resolves_then_render_failure():
    data = build_subbyte_fixture()
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    payload = to_payload(result, data, 0.0)
    assert payload["candidates"][0]["render"] == {"failure": FIXTURE_REASON}


def test_all_subbyte_multichannel_combinations_refused():
    """Property 7 (Requirement 6.5), exhaustive: BitsPerSample 1 to 7 by SamplesPerPixel 2 to 8."""
    for bps in range(1, 8):
        for spp in range(2, 9):
            for pi in (0, 1, 2, 3, None):
                depth = bps * spp
                r = decode(bytes(64), 4, 4, depth, 8, "tiff", photometric_interpretation=pi,
                           bits_per_sample=bps, samples_per_pixel=spp)
                assert r == RenderFailure(f"no renderer for TIFF with {spp} samples per pixel of {bps} bits each")


def test_subbyte_wins_over_palette_failure():
    """Requirement 6.2: 6.1 first when Requirement 3.4 also applies."""
    r = decode(bytes(16), 2, 2, 8, 2, "tiff", photometric_interpretation=3, bits_per_sample=4, samples_per_pixel=2)
    assert r == RenderFailure("no renderer for TIFF with 2 samples per pixel of 4 bits each")


def test_other_probes_and_values_not_refused():
    for kw in ({"bits_per_sample": 8, "samples_per_pixel": 2}, {"bits_per_sample": 4, "samples_per_pixel": 1},
               {"bits_per_sample": 0, "samples_per_pixel": 3}, {"bits_per_sample": True, "samples_per_pixel": 3},
               {"bits_per_sample": 4, "samples_per_pixel": None}):
        r = decode(bytes(16), 2, 2, 8, 2, "tiff", **kw)
        assert not (isinstance(r, RenderFailure) and r.reason.startswith("no renderer for TIFF with"))
    r = decode(bytes(16), 2, 2, 8, 2, "tga", bits_per_sample=4, samples_per_pixel=2)
    assert isinstance(r, PixelBuffer)


_maybe_int = st.one_of(st.none(), st.integers(-10, 70000), st.booleans(), st.text(max_size=3))


@settings(max_examples=300, deadline=None)
@given(decoded=st.one_of(st.binary(max_size=200), st.none()),
       width=st.integers(-2, 12), height=st.integers(-2, 12), depth=st.integers(-2, 70),
       stride=st.integers(-2, 40), probe=st.sampled_from(["tiff", "tga", "pcx", "pnm", "generic"]),
       color_map=st.one_of(st.none(), st.lists(st.integers(-5, 70000), max_size=20)),
       bps=_maybe_int, spp=_maybe_int, pi=_maybe_int, it=_maybe_int, idesc=_maybe_int)
def test_decode_never_raises_with_new_arguments(decoded, width, height, depth, stride, probe,
                                                color_map, bps, spp, pi, it, idesc):
    """Property 8, never-raises clause (Requirement 6.6)."""
    r = decode(decoded, width, height, depth, stride, probe, color_map=color_map, bits_per_sample=bps,
               samples_per_pixel=spp, photometric_interpretation=pi, image_type=it, image_descriptor=idesc)
    assert isinstance(r, (PixelBuffer, RenderFailure))
    assert not (isinstance(r, RenderFailure) and r.reason.startswith("internal error"))


def test_decode_equals_golden_when_no_new_argument_passed():
    """Property 8, "same as before" clause (Requirement 6.4): golden results taken from the code before this change."""
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(cases) == 400
    for c in cases:
        kw = dict(c["kw"])
        if kw["byte_order"]:
            kw["byte_order"] = kw["byte_order"].encode()
        r = decode(bytes.fromhex(c["data"]), c["w"], c["h"], c["depth"], c["stride"], c["probe"], **kw)
        assert _outcome(r) == c["result"]


def test_pixels_module_does_not_import_the_engine():
    """Requirement 7.2."""
    text = (ROOT / "web" / "pixels.py").read_text(encoding="utf-8")
    assert "necropsy.engine" not in text
    assert "import necropsy" not in text and "from necropsy" not in text


def test_no_sample_or_corpus_file_gets_the_subbyte_refusal():
    """Requirement 6.7: Samples and Real_Corpus render exactly as before."""
    for name, path in fc_diff.sample_paths() + fc_diff.corpus_paths():
        data = path.read_bytes()
        payload = to_payload(Engine().run(data), data, 0.0)
        for c in payload.get("candidates", []):
            reason = c["render"].get("failure", "")
            assert not reason.startswith("no renderer for TIFF with"), name


# ---- task 4.1: palette branch of decode (Requirements 2.1 to 2.4, 2.6, 3.1 to 3.5, 3.7, 3.8, 3.10 to 3.13) ----
from web.pixels import _palette_index_failure  # noqa: E402

PAL_NOTE = "8-bit · palette: TIFF ColorMap (tag 320), 768 values, 16-bit to 8-bit by v >> 8"
STORED = "rows shown in stored order"


def _pal(decoded, w, h, stride, cmap, **kw):
    args = dict(color_map=cmap, bits_per_sample=8, samples_per_pixel=1, photometric_interpretation=3)
    args.update(kw)
    return decode(decoded, w, h, 8, stride, "tiff", **args)


def _map(seed=1):
    """768 words: reds i*257 % 65536 style spread, built so every channel and index differs."""
    return tuple((i * 257 * seed + i) % 65536 for i in range(768))


def test_palette_exact_pixels_example():
    cmap = _map()
    # 3 x 2 raster, row stride 5 (2 padding bytes per row); indices by row: [0, 1, 255], [7, 7, 128]
    raw = bytes([0, 1, 255, 9, 9, 7, 7, 128, 9, 9])
    r = _pal(raw, 3, 2, 5, cmap)
    assert isinstance(r, PixelBuffer) and r.channels == "rgb8" and (r.width, r.height) == (3, 2)
    expect = b"".join(bytes((cmap[i] >> 8, cmap[256 + i] >> 8, cmap[512 + i] >> 8))
                      for i in (0, 1, 255, 7, 7, 128))
    assert r.data == expect
    assert r.note == PAL_NOTE + " · " + STORED


def test_palette_bottom_left_flips_rows():
    cmap = _map()
    r = _pal(bytes([0, 1, 2, 3]), 2, 2, 2, cmap, bottom_left=True)
    expect = b"".join(bytes((cmap[i] >> 8, cmap[256 + i] >> 8, cmap[512 + i] >> 8)) for i in (2, 3, 0, 1))
    assert r.data == expect
    assert r.note.endswith("rows flipped: file declares bottom-left origin")


@settings(max_examples=200, deadline=None)
@given(cmap=st.lists(st.integers(0, 65535), min_size=768, max_size=768),
       w=st.integers(1, 64), pad=st.integers(0, 3), data=st.data())
def test_palette_exact_pixels_property(cmap, w, pad, data):
    """Property 3 (Requirement 2.6)."""
    h = data.draw(st.integers(1, max(1, 4096 // w)))
    stride = w + pad
    idx = data.draw(st.lists(st.integers(0, 255), min_size=w * h, max_size=w * h))
    raw = b"".join(bytes(idx[y * w:(y + 1) * w]) + bytes(pad) for y in range(h))
    r = _pal(raw, w, h, stride, tuple(cmap))
    assert isinstance(r, PixelBuffer) and r.channels == "rgb8"
    assert len(r.data) == 3 * w * h
    expect = b"".join(bytes((cmap[i] >> 8, cmap[256 + i] >> 8, cmap[512 + i] >> 8)) for i in idx)
    assert r.data == expect


def test_palette_pinned_failure_strings():
    cmap = _map()
    raw = bytes(4)
    assert _pal(raw, 2, 2, 2, cmap, bits_per_sample=None) == RenderFailure(
        "no renderer for palette TIFF: BitsPerSample not recorded")
    for bps in (1, 2, 4, 16):
        assert _pal(raw, 2, 2, 2, cmap, bits_per_sample=bps) == RenderFailure(
            f"no renderer for palette TIFF: BitsPerSample {bps}")
    assert _pal(raw, 2, 2, 2, cmap, samples_per_pixel=3) == RenderFailure(
        "no renderer for palette TIFF with SamplesPerPixel 3")
    assert _pal(raw, 2, 2, 2, None) == RenderFailure("palette TIFF: no ColorMap (tag 320) was read")
    assert _pal(raw, 2, 2, 2, cmap[:195]) == RenderFailure(
        "palette TIFF: ColorMap (tag 320) holds 195 values, 768 required (3 × 2^8)")
    bad = list(cmap)
    bad[300] = 65536
    assert _pal(raw, 2, 2, 2, tuple(bad)) == RenderFailure(
        "palette TIFF: ColorMap (tag 320) entry 300 is 65536, outside 0 to 65535")
    bad[300], bad[5] = 7, -1
    assert _pal(raw, 2, 2, 2, tuple(bad)) == RenderFailure(
        "palette TIFF: ColorMap (tag 320) entry 5 is -1, outside 0 to 65535")
    bad[5] = True
    assert isinstance(_pal(raw, 2, 2, 2, tuple(bad)), RenderFailure)
    assert _pal(bytes(3), 2, 2, 2, cmap) == RenderFailure("inconsistent geometry")


def test_palette_bit_depth_must_equal_8_times_samples_per_pixel():
    """Requirement 3.13 (fixture built in code, decode called directly)."""
    cmap = _map()
    raw = bytes(8)
    r = decode(raw, 2, 2, 16, 4, "tiff", color_map=cmap, bits_per_sample=8, samples_per_pixel=1,
               photometric_interpretation=3)
    assert r == RenderFailure("no renderer for palette TIFF: bit depth 16 is not 8 × SamplesPerPixel 1")
    r = decode(raw, 2, 2, 8, 2, "tiff", color_map=cmap, bits_per_sample=8, samples_per_pixel=None,
               photometric_interpretation=3)
    assert r == RenderFailure("no renderer for palette TIFF: bit depth 8, SamplesPerPixel not recorded")
    for spp in (0, -1):
        r = decode(raw, 2, 2, 8, 2, "tiff", color_map=cmap, bits_per_sample=8, samples_per_pixel=spp,
                   photometric_interpretation=3)
        assert r == RenderFailure(
            f"no renderer for palette TIFF: bit depth 8 is not 8 × SamplesPerPixel {spp}")
    ok = decode(raw, 2, 2, 8, 2, "tiff", color_map=cmap, bits_per_sample=8, samples_per_pixel=1,
                photometric_interpretation=3)
    assert isinstance(ok, PixelBuffer)


def test_palette_failure_order():
    """Requirement 3.8: 4, 10, 13, 1, 2, 11, 3."""
    short = (70000,) * 10          # wrong count and out-of-range
    call = lambda **kw: decode(bytes(4), 2, 2, kw.pop("depth", 8), 2, "tiff", photometric_interpretation=3, **kw)
    # BitsPerSample 16 (not 1 to 7, so Requirement 6.1 does not apply first)
    assert "BitsPerSample 16" in call(color_map=short, bits_per_sample=16, samples_per_pixel=3, depth=99).reason
    assert "SamplesPerPixel 3" in call(color_map=short, bits_per_sample=8, samples_per_pixel=3, depth=99).reason
    assert "not 8 × SamplesPerPixel 1" in call(color_map=None, bits_per_sample=8, samples_per_pixel=1, depth=99).reason
    assert "no ColorMap" in call(color_map=None, bits_per_sample=8, samples_per_pixel=1).reason
    assert "holds 10 values" in call(color_map=short, bits_per_sample=8, samples_per_pixel=1).reason
    out_of_range = (70000,) + (0,) * 767
    assert "entry 0 is 70000" in call(color_map=out_of_range, bits_per_sample=8, samples_per_pixel=1).reason


def test_palette_index_failure_helper_with_small_map():
    """Requirement 3.3 through the helper (Decision 18)."""
    assert _palette_index_failure(bytes([0, 1, 2, 3]), 4) is None
    assert _palette_index_failure(b"", 4) is None
    assert _palette_index_failure(bytes([0, 9, 5, 4]), 4) == RenderFailure(
        "palette TIFF: pixel index 9 is at or above the ColorMap size 4")
    assert _palette_index_failure(bytes([1, 4, 200]), 4).reason.startswith("palette TIFF: pixel index 4 ")


@settings(max_examples=200, deadline=None)
@given(idx=st.binary(max_size=64), size=st.integers(1, 256))
def test_palette_index_failure_first_index_rule(idx, size):
    r = _palette_index_failure(idx, size)
    bad = [v for v in idx if v >= size]
    if not bad:
        assert r is None
    else:
        assert r == RenderFailure(f"palette TIFF: pixel index {bad[0]} is at or above the ColorMap size {size}")


@settings(max_examples=300, deadline=None)
@given(decoded=st.one_of(st.binary(max_size=300), st.none()),
       width=st.integers(-2, 20), height=st.integers(-2, 20), depth=st.integers(-2, 70),
       stride=st.integers(-2, 40),
       cmap=st.one_of(st.none(), st.lists(st.integers(-5, 70000), max_size=1024),
                      st.lists(st.integers(0, 65535), min_size=768, max_size=768)),
       bps=st.one_of(st.none(), st.integers(0, 65535)),
       spp=st.one_of(st.none(), st.integers(-3, 10)),
       bl=st.booleans())
def test_palette_never_raises_and_never_grey(decoded, width, height, depth, stride, cmap, bps, spp, bl):
    """Property 4 / Requirement 3.5, 3.7."""
    r = decode(decoded, width, height, depth, stride, "tiff", bottom_left=bl, color_map=cmap,
               bits_per_sample=bps, samples_per_pixel=spp, photometric_interpretation=3)
    assert isinstance(r, (PixelBuffer, RenderFailure))
    if isinstance(r, PixelBuffer):
        assert r.channels == "rgb8"
    else:
        assert not r.reason.startswith("internal error")


# ---- task 4.2: 16-bit TGA branches of decode (Requirements 4.1 to 4.6, 4.8, 4.9, 5.1 to 5.4, 5.6) ----
import struct  # noqa: E402

COLOUR_PREFIX = ("16-bit colour TGA · five-five-five, R bits 10-14, G bits 5-9, B bits 0-4 · v×255//31"
                 " · alpha not drawn: ")
GREY_NOTE = "16-bit grey TGA · grey = low byte of each word · the 8 declared alpha bits are not drawn"
STORED = "rows shown in stored order"
FLIPPED = "rows flipped: file declares bottom-left origin"


def _tga(raw, w, h, stride, it, desc, bl=False):
    return decode(raw, w, h, 16, stride, "tga", bottom_left=bl, image_type=it, image_descriptor=desc)


def _words(ws, pad=0):
    return b"".join(struct.pack("<H", w) for w in ws) + bytes(pad)


def _e5(v):
    return v * 255 // 31


def _colour_model(rows_of_words, flip):
    """Per-pixel definition of Requirement 4.1, computed from the words (not from decode)."""
    rows = rows_of_words[::-1] if flip else rows_of_words
    out = bytearray()
    for row in rows:
        for w in row:
            out += bytes((_e5((w >> 10) & 31), _e5((w >> 5) & 31), _e5(w & 31)))
    return bytes(out)


def test_tga16_colour_pillow_rgba16_pixels():
    """Decision 4 values: (21, 0, 31) -> (172, 0, 255); (0, 31, 10) -> (0, 255, 82); descriptor 0x08."""
    w1 = (21 << 10) | (0 << 5) | 31
    w2 = (0 << 10) | (31 << 5) | 10
    r = _tga(_words([w1, w2]), 2, 1, 4, 2, 0x08)
    assert isinstance(r, PixelBuffer) and r.channels == "rgb8"
    assert r.data == bytes((172, 0, 255, 0, 255, 82))
    assert r.note == (COLOUR_PREFIX + "descriptor declares 8 alpha bits, which the 16-bit pixel cannot hold;"
                      " bit 15 is not interpreted · " + FLIPPED)


def test_tga16_colour_alpha_notes():
    raw = _words([0x1234])
    cases = {0: "descriptor declares no alpha bits", 1: "descriptor declares bit 15 as alpha",
             2: "descriptor declares 2 alpha bits, which the 16-bit pixel cannot hold; bit 15 is not interpreted",
             15: "descriptor declares 15 alpha bits, which the 16-bit pixel cannot hold; bit 15 is not interpreted"}
    for a, text in cases.items():
        r = _tga(raw, 1, 1, 2, 2, 0x20 | a)
        assert isinstance(r, PixelBuffer), a
        assert r.note == COLOUR_PREFIX + text + " · " + STORED
    r = _tga(raw, 1, 1, 2, 10, None, bl=True)       # no descriptor: origin from `bottom_left`
    assert isinstance(r, PixelBuffer)
    assert r.note == COLOUR_PREFIX + "image descriptor not recorded · " + FLIPPED


@settings(max_examples=200, deadline=None)
@given(alpha=st.integers(0, 15), bit5=st.integers(0, 1), it=st.sampled_from([2, 10]),
       w=st.integers(1, 64), pad=st.integers(0, 3), data=st.data())
def test_tga16_colour_exact_pixels_property(alpha, bit5, it, w, pad, data):
    """Property 5 (Requirements 4.1, 4.2, 4.6, 4.8): any Alpha_Bits, either origin, bit 15 either value."""
    h = data.draw(st.integers(1, max(1, 4096 // w)))
    rows = [data.draw(st.lists(st.integers(0, 65535), min_size=w, max_size=w)) for _ in range(min(h, 8))]
    h = len(rows)
    raw = b"".join(_words(r, pad) for r in rows)
    r = _tga(raw, w, h, 2 * w + pad, it, (bit5 << 5) | alpha)
    assert isinstance(r, PixelBuffer) and r.channels == "rgb8"
    assert (r.width, r.height) == (w, h)
    assert r.data == _colour_model(rows, flip=(bit5 == 0))
    assert len(r.data) == 3 * w * h
    assert (FLIPPED if bit5 == 0 else STORED) in r.note
    assert "alpha not drawn" in r.note


def test_tga16_grey_low_byte_and_origin():
    rows = [[0x0102, 0xFF03], [0x0004, 0x80FF], [0xAB10, 0x0020]]
    raw = b"".join(_words(r, 2) for r in rows)
    r = _tga(raw, 2, 3, 6, 3, 0x08)                         # bit 5 = 0: bottom-left
    assert isinstance(r, PixelBuffer) and r.channels == "grey8"
    assert r.data == bytes(w & 0xFF for row in rows[::-1] for w in row)
    assert r.note == GREY_NOTE + " · " + FLIPPED
    r = _tga(raw, 2, 3, 6, 11, 0x28)                        # bit 5 = 1: stored order
    assert r.data == bytes(w & 0xFF for row in rows for w in row)
    assert r.note == GREY_NOTE + " · " + STORED


@settings(max_examples=200, deadline=None)
@given(bit5=st.integers(0, 1), it=st.sampled_from([3, 11]), w=st.integers(1, 32), pad=st.integers(0, 3),
       rows=st.lists(st.lists(st.integers(0, 65535), min_size=32, max_size=32), min_size=1, max_size=8))
def test_tga16_grey_exact_pixels_property(bit5, it, w, pad, rows):
    """Property 6, drawn case (Requirements 5.1, 5.4, 5.6)."""
    rows = [r[:w] for r in rows]
    raw = b"".join(_words(r, pad) for r in rows)
    r = _tga(raw, w, len(rows), 2 * w + pad, it, (bit5 << 5) | 8)
    assert isinstance(r, PixelBuffer) and r.channels == "grey8"
    order = rows[::-1] if bit5 == 0 else rows
    assert r.data == bytes(x & 0xFF for row in order for x in row)


def test_tga16_grey_refused_unless_alpha_bits_8():
    """Property 6, refusal (Requirement 5.3)."""
    for a in [*range(0, 8), *range(9, 16)]:
        r = _tga(_words([1, 2]), 2, 1, 4, 3, 0x20 | a)
        assert r == RenderFailure(
            f"no renderer for 16-bit grey TGA: the descriptor declares {a} alpha bits, 8 are required")
    assert _tga(_words([1, 2]), 2, 1, 4, 11, None) == RenderFailure(
        "no renderer for 16-bit grey TGA: image descriptor not recorded")


def test_tga16_short_data_failures():
    assert _tga(bytes(7), 2, 2, 4, 2, 0x20) == RenderFailure("16-bit colour TGA: pixel data holds 7 bytes, 8 required")
    assert _tga(bytes(7), 2, 2, 4, 10, 0x20) == RenderFailure("16-bit colour TGA: pixel data holds 7 bytes, 8 required")
    assert _tga(bytes(7), 2, 2, 4, 3, 0x28) == RenderFailure("16-bit grey TGA: pixel data holds 7 bytes, 8 required")
    assert _tga(bytes(8), 3, 1, 2, 2, 0x20) == RenderFailure("inconsistent geometry")


def test_tga16_not_taken_for_other_inputs():
    """No image_type (not yet wired) and other types keep the old answer."""
    assert decode(bytes(8), 2, 2, 16, 4, "tga") == RenderFailure("no renderer for 16-bit pixels")
    assert decode(bytes(8), 2, 2, 16, 4, "tga", image_type=1, image_descriptor=0x20) == \
        RenderFailure("no renderer for 16-bit pixels")
    assert decode(bytes(8), 2, 2, 16, 4, "pcx", image_type=2, image_descriptor=0x20) == \
        RenderFailure("no renderer for 16-bit pixels")


@settings(max_examples=300, deadline=None)
@given(decoded=st.binary(max_size=200), width=st.integers(-2, 12), height=st.integers(-2, 12),
       stride=st.integers(-2, 40), it=st.one_of(st.none(), st.integers(0, 12)),
       idesc=st.one_of(st.none(), st.integers(-3, 300)), bl=st.booleans())
def test_tga16_decode_never_raises(decoded, width, height, stride, it, idesc, bl):
    r = decode(decoded, width, height, 16, stride, "tga", bottom_left=bl, image_type=it, image_descriptor=idesc)
    assert isinstance(r, (PixelBuffer, RenderFailure))
    if isinstance(r, RenderFailure):
        assert not r.reason.startswith("internal error")


# ---- task 5.1: the Serialiser passes color_map and photometric_interpretation (Requirements 2.5, 2.7, 3.6, 3.9, 7.1) ----
from types import SimpleNamespace  # noqa: E402

from necropsy.engine.types import FieldRecord  # noqa: E402
from web.serialise import _int_field, color_map_for  # noqa: E402


def _cand(fields):
    return SimpleNamespace(hypothesis=SimpleNamespace(fields=tuple(fields)))


_values = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=4), st.binary(max_size=4),
                    st.tuples(st.integers(), st.integers()), st.tuples(st.booleans()), st.tuples(st.text(max_size=2)),
                    st.lists(st.integers(0, 65535), max_size=8).map(tuple))


@settings(max_examples=200, deadline=None)
@given(value=_values, name=st.sampled_from(["color_map", "photometric_interpretation", "other"]))
def test_color_map_for_and_int_field_are_total_and_integers_only(value, name):
    """Property 9 (Requirement 2.5): total, integers only (a bool is not an integer), else None."""
    c = _cand([FieldRecord(name, 0, "<H", value)])
    cm = color_map_for(c)
    assert cm is None or (isinstance(cm, tuple) and all(type(x) is int for x in cm))
    n = _int_field(c, name)
    assert n is None or type(n) is int
    if name == "color_map" and isinstance(value, tuple) and all(type(x) is int for x in value):
        assert cm == value
    elif name == "color_map":
        assert cm is None
    assert color_map_for(_cand([])) is None


def test_color_map_in_payload_once_and_two_palette_files_draw_rgb8():
    """Requirements 2.5, 2.7: one color_map field entry; the render is rgb8 with the pinned note."""
    for name, size in (("libtiff_palette-1c-8b.tiff", (157, 151)), ("goimage_video-001-paletted.tiff", (150, 103))):
        data = (fc_diff.REAL / name).read_bytes()
        result = Engine().run(data)
        p = to_payload(result, data, 0.0)
        c = p["candidates"][0]
        assert [f["name"] for f in c["fields"]].count("color_map") == 1
        r = c["render"]
        assert (r["channels"], r["width"], r["height"]) == ("rgb8", *size)
        assert r["note"].startswith(PAL_NOTE)
        # one pixel's colour from the candidate's own ColorMap, computed here and not by decode
        cm = color_map_for(result.candidate)
        import base64
        raw = base64.b64decode(r["data_b64"])
        idx = result.candidate.decoded[0]
        assert tuple(raw[:3]) == (cm[idx] >> 8, cm[256 + idx] >> 8, cm[512 + idx] >> 8)


def test_invalid_palette_ref_is_a_render_failure_with_195_and_768():
    """Requirements 3.6, 3.9: no picture, the reason stated, no data_b64."""
    data = (fc_diff.REAL / "goimage_invalid-palette-ref.tiff").read_bytes()
    r = to_payload(Engine().run(data), data, 0.0)["candidates"][0]["render"]
    assert r == {"failure": "palette TIFF: ColorMap (tag 320) holds 195 values, 768 required (3 × 2^8)"}
