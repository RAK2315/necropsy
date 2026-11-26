"""Differential test over spike/samples/real/ (real-corpus spec).

Expectations are stated here, not read from the engine:
- every out-of-scope file is FAILED, with its termination recorded;
- of the six invalid-by-construction files, five FAIL and ossfuzz RESOLVES with a literal two-pixel reading;
- every in-scope valid file RESOLVES and its pixels equal Pillow's.
Five in-scope files do not meet the last expectation today. They are strict xfails under diagnosis elsewhere;
they flip to errors when fixed, which is the cue to regenerate the table.

Pillow is not needed in CI: the committed results hold Pillow's canonical pixel hash. With Pillow installed, a
separate test checks those hashes against a live decode.
"""
import hashlib
import json

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tools import real_corpus as rc

MANIFEST = {e["file"]: e for e in rc.load_manifest()}
COMMITTED = {r["file"]: r for r in json.loads(rc.OUT.read_text(encoding="utf-8"))}
OSSFUZZ = "pillow_ossfuzz-4836216264589312.pcx"
RGBA16 = "pillow_rgba16.tga"
CROSS_SCAN = "pillow_cross_scan_line.tga"
FILES = sorted(MANIFEST)


def scope_of(name):
    return MANIFEST[name]["scope"]


_RUNS = {}


def run(name):
    if name not in _RUNS:
        data = (rc.REAL / name).read_bytes()
        _RUNS[name] = (data, Engine().run(data))
    return _RUNS[name]


def test_corpus_is_all_81_files_and_unmodified():
    assert len(MANIFEST) == 81
    for name, e in MANIFEST.items():
        assert hashlib.sha256((rc.REAL / name).read_bytes()).hexdigest() == e["sha256"], name


def test_scope_counts():
    scopes = [scope_of(n) for n in FILES]
    assert scopes.count("in") == 27 and scopes.count("out") == 54
    assert len(rc.INVALID_BY_CONSTRUCTION) == 6


@pytest.mark.parametrize("name", FILES)
def test_committed_results_match_a_live_run(name):
    data, result = run(name)
    row = COMMITTED[name]
    assert row["our_status"] == result.status
    assert row["termination"] == getattr(result, "termination", None)
    assert row["checks"] == result.total_checks
    assert row["candidates"] == [rc.describe(c) for c in rc.candidates_of(result)]


# format-coverage Requirement 3.8 and design.md row 4: the binary PNM probe resolves these nine files. The manifest
# scope is rewritten from header bytes in format-coverage Task 37, so for now they are carved out here.
PNM_RESOLVED = {
    "imagemagick_input_p5.pgm", "imagemagick_input_p6.ppm", "libtiff_minisblack-1c-8b.pgm",
    "libtiff_rgb-3c-16b.ppm", "libtiff_rgb-3c-8b.ppm", "pillow_hopper_16bit.pgm",
    "pillow_hopper_8bit.pgm", "pillow_hopper_8bit.ppm", "sdlimage_sample.pnm",
}
# format-coverage Requirement 4.1, 4.2, 4.4, 4.13 and design.md row 8: the text PNM probe resolves these four files.
PNM_TEXT_RESOLVED = {
    "imagemagick_input_p1.pbm", "imagemagick_input_p2.pgm", "imagemagick_input_p3.ppm",
    "pillow_hopper_1bit_plain.pbm",
}
# format-coverage Requirement 5.8, 5.9 and design.md row 11: rle_tga is decoded; these six files resolve. The seventh
# predicted file, pillow_cross_scan_line.tga, stays FAILED and is an open in-scope failure (Task 12; see
# tools/real_corpus.py). The manifest scope of these six is rewritten from header bytes in Task 37.
RLE_TGA_RESOLVED = {
    "pillow_200x32_l_tl_rle.tga", "pillow_200x32_p_tl_rle.tga", "pillow_200x32_rgb_tl_rle.tga",
    "pillow_la.tga", "pillow_rgb32rle.tga", "sdlimage_sample.tga",
}
# format-coverage Requirement 6.2, 6.6 and design.md row 15: the multi-plane PCX seed resolves these three files. Their
# manifest scope is rewritten from header bytes in Task 37; the pixel comparer learns planar PCX in Task 38.
PCX_PLANAR_RESOLVED = {"imagemagick_input.pcx", "pillow_p_4_planes.pcx", "sdlimage_sample.pcx"}
# format-coverage Requirement 8.1 to 8.4, 8.9, 8.11 and design.md row 18: the strip-array probe resolves these six
# uncompressed multi-strip TIFFs. Their manifest scope is rewritten in Task 37; the pixel comparer and the render of
# the 12-bit file (Task 19) are not part of this task.
TIFF_STRIPS_RESOLVED = {
    "goimage_video-001-gray.tiff", "libtiff_minisblack-1c-8b.tiff", "libtiff_palette-1c-8b.tiff",
    "libtiff_rgb-3c-8b.tiff", "pillow_12bit.cropped.tif", "pillow_tiff_strip_raw.tif",
}
# format-coverage Requirement 9.1 to 9.6 and design.md row 21: the tile-array probe resolves this uncompressed tiled
# TIFF. Its manifest scope is rewritten in Task 37; the full TIFF expectations belong to Task 28.
TIFF_TILES_RESOLVED = {"pillow_tiff_tiled_raw.tif"}
# format-coverage Requirement 11.1 to 11.7 and design.md row 23: the PackBits decoder resolves this strip TIFF. Its manifest
# scope is rewritten in Task 37; the full TIFF expectations belong to Task 28. Pixel comparison is pending: the comparer
# in tools/real_corpus.py does not handle tiff_compression_32773 yet (row carries "not comparable").
TIFF_PACKBITS_RESOLVED = {"goimage_bw-packbits.tiff"}
# format-coverage Requirement 12.1 to 12.10 and design.md row 24: the LZW decoder resolves this 6-strip TIFF. Its manifest
# scope is rewritten in Task 37; the full TIFF expectations belong to Task 28. Pixel comparison is pending: the comparer
# in tools/real_corpus.py does not handle tiff_compression_5 yet (row carries "not comparable").
# libtiff_lzw-single-strip.tiff, also listed in row 24, ends without EOI: 3,043,950 bytes out, 5 bits left at width 10.
# Requirement 12.8 (b), as amended (Decision Record item 33 of the engine spec), accepts that end.
TIFF_LZW_RESOLVED = {"goimage_blue-purple-pink.lzwcompressed.tiff", "libtiff_lzw-single-strip.tiff"}
OUT_OF_SCOPE = [n for n in FILES if scope_of(n) == "out" and n != OSSFUZZ and n not in TIFF_TILES_RESOLVED
                and n not in PNM_RESOLVED and n not in PNM_TEXT_RESOLVED and n not in RLE_TGA_RESOLVED
                and n not in PCX_PLANAR_RESOLVED and n not in TIFF_STRIPS_RESOLVED
                and n not in TIFF_PACKBITS_RESOLVED and n not in TIFF_LZW_RESOLVED]


@pytest.mark.parametrize("name", sorted(TIFF_STRIPS_RESOLVED))
def test_tiff_strip_files_resolve(name):
    # Requirement 8.1 to 8.4, 8.9, 8.11; format-coverage Task 18.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(TIFF_TILES_RESOLVED))
def test_tiff_tile_files_resolve(name):
    # Requirement 9.1 to 9.6; format-coverage Task 21.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(TIFF_PACKBITS_RESOLVED))
def test_tiff_packbits_files_resolve(name):
    # Requirement 11.1 to 11.7; format-coverage Task 23.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(TIFF_LZW_RESOLVED))
def test_tiff_lzw_files_resolve(name):
    # Requirement 12.1 to 12.10; format-coverage Task 24.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(PCX_PLANAR_RESOLVED))
def test_multi_plane_pcx_files_resolve(name):
    # Requirement 6.2, 6.6; format-coverage Task 15.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(RLE_TGA_RESOLVED))
def test_rle_tga_files_resolve(name):
    # Requirement 5.8, 5.9; format-coverage Task 11.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(PNM_RESOLVED))
def test_binary_pnm_files_resolve(name):
    # Requirement 3.8: the probe's candidate closes; format-coverage Task 4.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", sorted(PNM_TEXT_RESOLVED))
def test_text_pnm_files_resolve(name):
    # Requirement 4.1, 4.2, 4.4: the exact-count rule holds for these files; format-coverage Task 8.
    assert run(name)[1].status == "RESOLVED"


@pytest.mark.parametrize("name", OUT_OF_SCOPE)
def test_out_of_scope_is_a_stated_refusal(name):
    _, result = run(name)
    assert result.status == "FAILED", f"{name} returned {result.status}"
    assert result.termination in ("exhausted", "no_hypothesis_checked")


@pytest.mark.parametrize("name", [n for n in rc.INVALID_BY_CONSTRUCTION if n != OSSFUZZ])
def test_five_invalid_files_fail(name):
    assert run(name)[1].status == "FAILED"


def test_ossfuzz_resolves_with_a_literal_reading_and_a_file_layout_spec():
    data, result = run(OSSFUZZ)
    assert len(data) == 129 and data[0] == 0x0A and data[2] == 0x20
    assert result.status == "RESOLVED" and result.stage == "generic"
    h = result.candidate.hypothesis
    assert (h.width, h.height, h.bit_depth, h.header_size, h.row_alignment, h.encoding) == (2, 1, 1, 128, 1, "none")
    assert (result.candidate.data_start, result.candidate.data_end) == (128, 129)
    # Engine Requirement 7.15 / real-corpus Requirement 4.3: the PCX probe recognised the signature and declined
    # because encoding byte 0x20 has no reading, recording exactly one probe_precondition_failed.
    assert len(result.rejections) == 1
    rej = result.rejections[0]
    assert rej.reason == "probe_precondition_failed"
    assert rej.source == "pcx"
    assert rej.hypothesis is None
    assert "0x02" in rej.detail and "0x20" in rej.detail
    assert h.probe_name == "generic"
    # The emitted spec describes this one file, not the PCX format.
    requirements = dict(emit_spec(result, data).files)["requirements.md"]
    assert 'layout kind `file`' in requirements
    assert "this one file only" in requirements.lower() or "This is the layout of this one file only" in requirements


IN_SCOPE_VALID = [n for n in FILES if scope_of(n) == "in" and n not in rc.INVALID_BY_CONSTRUCTION]
OPEN = set(rc.OPEN_IN_SCOPE_FAILURES)
RECOVERABLE = [n for n in IN_SCOPE_VALID if n not in OPEN and n != RGBA16]


def canon(name):
    data, result = run(name)
    assert result.status == "RESOLVED", f"{name} returned {result.status}"
    ours = rc.ours_canonical(MANIFEST[name], data, result.candidate)
    assert isinstance(ours, tuple), ours
    return ours


@pytest.mark.parametrize("name", RECOVERABLE)
def test_in_scope_pixels_equal_pillows(name):
    ours = canon(name)
    committed = COMMITTED[name]["pillow_pixels_sha256"]
    assert committed is not None
    assert hashlib.sha256(ours[0]).hexdigest() == committed


def test_open_in_scope_failures_are_exactly_these():
    # format-coverage Task 12 (Requirement 5.9): one open failure, with the measured note.
    assert OPEN == {CROSS_SCAN}
    assert COMMITTED[CROSS_SCAN]["note"] == rc.NOTES[CROSS_SCAN]
    assert COMMITTED[CROSS_SCAN]["note"].startswith(
        "its RLE data needs one byte that lies inside its declared TGA 2.0 footer; "
        "Pillow decodes it because it ignores the footer")
    assert "invalid by construction" not in COMMITTED[CROSS_SCAN]["note"].lower()
    assert CROSS_SCAN not in rc.INVALID_BY_CONSTRUCTION
    assert scope_of(CROSS_SCAN) == "in"


def test_cross_scan_line_fails_under_both_readings_req_5_9():
    # 49 bytes: header 18, data 5, footer 26. Without the footer the data region is [18, 23) = 02 00 FF FF 00:
    # a raw packet of 3 pixels (00 FF FF) then a raw header (00) whose pixel byte would be byte 23, in the footer.
    from necropsy.engine.decoders import rle_tga_decode
    data = (rc.REAL / CROSS_SCAN).read_bytes()
    assert len(data) == 49 and data[18:23] == b"\x02\x00\xff\xff\x00"
    assert rle_tga_decode(data, 18, 23, 1, 4).status == "underrun"
    r = rle_tga_decode(data, 18, 49, 1, 4)
    assert r.status == "unconsumed"
    assert run(CROSS_SCAN)[1].status == "FAILED"


@pytest.mark.parametrize("name", sorted(OPEN))
@pytest.mark.xfail(strict=True, reason="in scope, valid, FAILED: its RLE data needs one byte inside its TGA 2.0 footer (Req 5.9)")
def test_open_in_scope_failures(name):
    assert run(name)[1].status == "RESOLVED"


def test_rgba16_differs_only_in_the_alpha_interpretation():
    ours = canon(RGBA16)[0]
    theirs = rc.pillow_canonical(rc.REAL / RGBA16, MANIFEST[RGBA16]) if rc_has_pillow() else None
    # Canonical form here is (r5, g5, b5, alpha bit) per pixel. Colour bits agree; the alpha bit is inverted.
    assert len(ours) == 8
    if theirs is not None:
        assert isinstance(theirs, tuple)
        assert all(a == b for i, (a, b) in enumerate(zip(ours, theirs[0])) if i % 4 != 3)
        assert all(a != b for i, (a, b) in enumerate(zip(ours, theirs[0])) if i % 4 == 3)
    assert COMMITTED[RGBA16]["pixel_verdicts"] == ["mismatch: 2 of 8 canonical bytes differ"]


def rc_has_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not rc_has_pillow(), reason="Pillow not installed")
@pytest.mark.parametrize("name", [n for n in IN_SCOPE_VALID if COMMITTED[n]["pillow_pixels_sha256"]])
def test_committed_pillow_hashes_hold_with_a_live_decode(name):
    theirs = rc.pillow_canonical(rc.REAL / name, MANIFEST[name])
    assert isinstance(theirs, tuple)
    assert hashlib.sha256(theirs[0]).hexdigest() == COMMITTED[name]["pillow_pixels_sha256"]
