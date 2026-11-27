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
