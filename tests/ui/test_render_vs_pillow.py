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
# "inverted_by_convention" (the file declares nothing; the two readers chose opposite conventions, and ours says so).
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
    "pillow_200x32_la_bl_raw.tga": ("no_renderer", "16-bit pixels have no renderer (Requirement 3.9)"),
    "pillow_rgba16.tga": ("no_renderer", "16-bit pixels have no renderer (Requirement 3.9)"),
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
    if kind == "no_renderer":
        assert render.get("failure", "").startswith("no renderer for"), reason
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
