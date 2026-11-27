"""Differential check of the recovered image (Requirement 3.17): the render against Pillow, pixel for pixel.

Every file in spike/samples, spike/samples/external and spike/samples/real that the engine RESOLVES is rendered exactly
as the web service renders it (web.serialise.to_payload) and compared with Pillow's decoding of the same bytes, as RGB.
A file that cannot be compared is listed in EXCEPTIONS with its reason, and its test asserts that the reason still holds,
so an exception that stops being true fails instead of hiding a difference.
"""
import base64
import io

import pytest

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from web.serialise import to_payload

Image = pytest.importorskip("PIL.Image")

DIRS = [REPO_ROOT / "spike" / "samples", REPO_ROOT / "spike" / "samples" / "external", REPO_ROOT / "spike" / "samples" / "real"]
NOT_SAMPLES = {"README.md", "manifest.json", ".gitattributes", "source.ppm"}

NO_PHOTOMETRIC = "no photometric interpretation declared; shown as BlackIsZero (0 = black)"

# name: (kind, reason). Kinds: "pillow_fails" (Pillow cannot decode the file), "no_renderer" (Requirement 3.9),
# "inverted_by_convention" (the file declares nothing; the two readers chose opposite conventions, and ours says so),
# "payload_limit" (the image is above the render's pixel budget, so nothing is rendered).
EXCEPTIONS = {
    "mystery_e": ("inverted_by_convention",
                  "declares no photometric interpretation: Pillow assumes WhiteIsZero, the render shows BlackIsZero and its "
                  "note says so; make_samples writes BlackIsZero (test_pixels.py checks that)"),
    "mystery_h": ("pillow_fails", "Pillow raises OSError (buffer overrun): rows padded to 4 bytes; checked against "
                                  "make_samples in test_pixels.py instead"),
    "pillow_ossfuzz-4836216264589312.pcx": ("pillow_fails", "Pillow raises OSError (image file is truncated)"),
    # Requirement 16.1 fixes the scaling of 16-bit PNM at v * 255 // maxval. Pillow differs by design: it rounds an RGB
    # sample to nearest, (v * 255 + 32767) // 65535, where we floor, and, for
    # grey, loads 16-bit as mode I, which convert("RGB") clips to 255. Each test asserts exactly that difference.
    "libtiff_rgb-3c-16b.ppm": ("pnm16_pillow_rounds", "Pillow rounds to nearest; Requirement 16.1 requires v * 255 // maxval"),
    "pillow_hopper_16bit.pgm": ("pnm16_pillow_clips", "Pillow's mode I clips to 255 on convert('RGB'); Requirement 16.1 requires "
                                                       "v * 255 // maxval"),
    # render-fidelity 5.2 (Requirements 4.7, 4.10, 5.5, 5.7, 9.2): pillow_200x32_la_bl_raw.tga, pillow_la.tga and
    # pillow_rgba16.tga are drawn through their 16-bit TGA branches (image_type and image_descriptor now reach decode), so
    # they are no longer exceptions: all three are compared with Pillow byte for byte.
    # format-coverage Task 18 (Requirement 8): these two TIFFs now resolve through the strip-array probe. Their renders are
    # pending: 12-bit grey belongs to Task 19 (Requirement 16.1 to 16.5); the TIFF palette is drawn since render-fidelity 5.1.
    # Task 19: rendered. Requirement 16.1 shows a 12-bit TIFF sample v as v * 255 // 4095; Pillow loads it as mode I;16 and
    # convert("RGB") clips to 255. The file's samples are all 30 or less, so ours is near black and Pillow's is v itself.
    "pillow_12bit.cropped.tif": ("tiff12_pillow_clips", "Pillow's I;16 clips to 255 on convert('RGB'); Requirement 16.1 "
                                                        "requires v * 255 // 4095"),
    # Requirement 12.8 (b): resolved since the LZW end rule was amended. 7795 x 3122 is 24.3 million pixels, above the
    # 500,000 pixel budget (Requirement 2.9), so the service sends no image. The engine's decoded bytes were compared with
    # Pillow's offline (26 Nov 2026: all 24,335,990 pixels equal).
    "libtiff_lzw-single-strip.tiff": ("payload_limit", "24.3 million pixels exceed the render's pixel budget (Requirement 2.9)"),
    # format-coverage Task 25 (Requirement 13.1, design.md row 25): Deflate TIFFs now resolve. goimage_invalid-palette-ref.tiff
    # decodes the same region as the paletted file; Pillow refuses it (UnidentifiedImageError, an OSError), and its render is
    # a RenderFailure stating 195 and 768 (render-fidelity Requirements 3.6 and 9.2, test below).
    # render-fidelity 5.1 (Requirements 2.5, 2.7, 9.2): goimage_video-001-paletted.tiff and libtiff_palette-1c-8b.tiff are
    # drawn through their ColorMap (tag 320), so they are no longer exceptions: both are compared with Pillow byte for byte.
    # goimage_bw-deflate.tiff needs no exception: web/pixels.py honours photometric 0
    # for 1-bit TIFF (_grey inverts WhiteIsZero), so its render equals Pillow's.
    "goimage_invalid-palette-ref.tiff": ("pillow_fails", "Pillow refuses the file (UnidentifiedImageError); design.md row 25"),
}


def _resolved_files():
    out = []
    for d in DIRS:
        for p in sorted(d.iterdir()):
            if p.is_file() and p.name not in NOT_SAMPLES:
                result = Engine().run(p.read_bytes())
                if result.status == "RESOLVED":
                    out.append(p)
    return out


RESOLVED = _resolved_files()


def _render(data):
    return to_payload(Engine().run(data), data, 1.0)["candidates"][0]["render"]


def _rgb(render) -> bytes:
    raw = base64.b64decode(render["data_b64"])
    return bytes(v for b in raw for v in (b, b, b)) if render["channels"] == "grey8" else raw


def _pillow(data):
    im = Image.open(io.BytesIO(data))
    im.load()
    return im.convert("RGB")


def test_every_exception_names_a_resolved_file():
    names = {p.name for p in RESOLVED}
    assert set(EXCEPTIONS) <= names, f"stale exceptions: {sorted(set(EXCEPTIONS) - names)}"
    assert len(RESOLVED) >= 30


@pytest.mark.parametrize("path", RESOLVED, ids=[p.name for p in RESOLVED])
def test_render_matches_pillow(path):
    data = path.read_bytes()
    render = _render(data)
    kind, reason = EXCEPTIONS.get(path.name, (None, None))
    if kind == "pillow_fails":
        with pytest.raises(OSError):
            _pillow(data)
        return
    if kind == "render_pending":
        # Fails once the render matches Pillow, which is the cue to remove the exception.
        assert "data_b64" not in render or _rgb(render) != _pillow(data).tobytes(), reason
        return
    if kind == "payload_limit":
        assert render.get("failure") == "not rendered: payload limit", reason
        return
    if kind == "no_renderer":
        assert render.get("failure", "").startswith("no renderer for"), reason
        return
    if kind == "tiff12_pillow_clips":
        c = Engine().run(data).candidate
        h, stride = c.hypothesis, c.row_stride
        assert h.bit_depth == 12 and h.probe_name == "tiff" and h.width * 12 % 8 == 0
        # Each row is `stride` bytes; a pair of samples is 3 bytes, MSB first (Requirement 16.1).
        words = []
        for y in range(h.height):
            row = c.decoded[y * stride: y * stride + h.width * 3 // 2]
            for i in range(0, len(row), 3):
                words += [(row[i] << 4) | (row[i + 1] >> 4), ((row[i + 1] & 15) << 8) | row[i + 2]]
        assert len(words) == h.width * h.height and max(words) <= 30
        assert _rgb(render) == bytes(v for w in words for v in [w * 255 // 4095] * 3), reason
        assert _pillow(data).tobytes() == bytes(v for w in words for v in [min(255, w)] * 3), reason
        assert _rgb(render) != _pillow(data).tobytes()
        return
    if kind in ("pnm16_pillow_rounds", "pnm16_pillow_clips"):
        # Both files have maxval 65535 and no trailer, so the samples are the last w*h*channels big-endian words.
        channels = 3 if kind == "pnm16_pillow_rounds" else 1
        n = render["width"] * render["height"] * channels
        words = [int.from_bytes(data[len(data) - 2 * n + 2 * i:len(data) - 2 * n + 2 * i + 2], "big") for i in range(n)]
        assert data[:2] == (b"P6" if channels == 3 else b"P5") and b"\n65535\n" in data[:64]
        spread = (lambda b: b) if channels == 3 else (lambda b: bytes(v for x in b for v in (x, x, x)))
        assert _rgb(render) == spread(bytes(v * 255 // 65535 for v in words)), reason
        theirs = _pillow(data).tobytes()
        known = bytes((v * 255 + 32767) // 65535 for v in words) if channels == 3 else bytes(min(255, v) for v in words)
        assert theirs == spread(known), reason
        assert _rgb(render) != theirs
        return
    assert "data_b64" in render, f"{path.name}: no image ({render.get('failure')})"
    ref = _pillow(data)
    assert (render["width"], render["height"]) == ref.size
    ours = _rgb(render)
    if kind == "inverted_by_convention":
        assert ours == bytes(255 - v for v in ref.tobytes()), reason
        assert NO_PHOTOMETRIC in render["note"], f"{path.name}: the note must name the convention: {render['note']!r}"
        return
    if ours != ref.tobytes():
        theirs = ref.tobytes()
        n = sum(1 for i in range(0, len(ours), 3) if ours[i:i + 3] != theirs[i:i + 3])
        pytest.fail(f"{path.name}: {n} of {len(ours) // 3} pixels differ from Pillow; note {render['note']!r}")


def test_invalid_palette_ref_render_is_a_failure_stating_195_and_768():
    # render-fidelity Requirements 3.6 and 9.2: the file declares 195 ColorMap values where 768 are required.
    path = next(p for p in RESOLVED if p.name == "goimage_invalid-palette-ref.tiff")
    render = _render(path.read_bytes())
    assert "data_b64" not in render
    assert "195" in render["failure"] and "768" in render["failure"], render
    assert render["failure"] == "palette TIFF: ColorMap (tag 320) holds 195 values, 768 required (3 × 2^8)"


def _tga16_render(name):
    path = next(p for p in RESOLVED if p.name == name)
    data = path.read_bytes()
    return Engine().run(data).candidate, _render(data), data


def test_16bit_tga_renders_come_from_the_candidate_fields():
    # render-fidelity 5.2 (Requirements 4.7, 4.10, 5.5, 5.7): kind, size and pixels of the three files.
    cand, r, _ = _tga16_render("pillow_200x32_la_bl_raw.tga")
    assert (r["channels"], r["width"], r["height"]) == ("grey8", 200, 32) and "rows flipped" in r["note"]
    cand, r, _ = _tga16_render("pillow_la.tga")
    assert (r["channels"], r["width"], r["height"]) == ("grey8", 64, 64) and "stored order" in r["note"]
    cand, r, data = _tga16_render("pillow_rgba16.tga")
    assert (r["channels"], r["width"], r["height"]) == ("rgb8", 2, 1)
    assert _rgb(r) == bytes([172, 0, 255, 0, 255, 82])
    assert r["note"].split("\u00b7")[-2].strip() == ("alpha not drawn: descriptor declares 8 alpha bits, which the 16-bit "
                                                      "pixel cannot hold; bit 15 is not interpreted")
    # image_type and image_descriptor are the candidate's FieldRecords (header bytes 2 and 17), not re-read from the file.
    fields = {f.name: f.value for f in cand.hypothesis.fields}
    assert fields["image_type"] == (data[2],) and fields["image_descriptor"] == (data[17],) and data[17] == 0x08


def _tga_16bit_map() -> bytes:
    """A colour-mapped TGA built from the documented layout, with every 5-bit level in every channel.

    Header (18 bytes): id_length 0; color_map_type 1; image_type 1 (uncompressed, colour-mapped); first entry 0 (<H at
    0x03); map length 32 (<H at 0x05); entry size 16 (0x07); x/y origin 0; width 32, height 1 (<H at 0x0C, 0x0E);
    8 bits per pixel (0x10); descriptor 0x20 (top-left). Map entry k is a little-endian uint16 holding B = k,
    G = 31 - k, R = (k * 7) % 32 in bits 0-4, 5-9 and 10-14. Pixel x has value x, so each entry is shown once.
    No sample file uses 5-bit levels other than 0 and 31, where every expansion agrees; this one does.
    """
    import struct
    header = struct.pack("<BBBHHBHHHHBB", 0, 1, 1, 0, 32, 16, 0, 0, 32, 1, 8, 0x20)
    entries = b"".join(struct.pack("<H", (((k * 7) % 32) << 10) | ((31 - k) << 5) | k) for k in range(32))
    return header + entries + bytes(range(32))


def test_16bit_colour_map_expansion_matches_pillow_at_every_level():
    data = _tga_16bit_map()
    result = Engine().run(data)
    assert result.status == "RESOLVED" and result.candidate.hypothesis.probe_name == "tga"
    render = _render(data)
    assert "colour map, 32 × 16-bit entries, first index 0 (0x03)" in render["note"]
    assert _rgb(render) == _pillow(data).tobytes()
