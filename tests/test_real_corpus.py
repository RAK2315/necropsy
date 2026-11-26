"""Differential test over spike/samples/real/ (real-corpus spec, format-coverage spec).

Scope is read from the manifest, which tools/scope_from_headers.py writes from header bytes (format-coverage
Requirement 18). Expectations are stated here, not read from the engine:
- every out-of-scope file is FAILED, with its termination recorded, except pillow_ossfuzz-4836216264589312.pcx, which
  RESOLVES with a literal two-pixel reading;
- of the six invalid-by-construction files, five FAIL and ossfuzz RESOLVES; goimage_invalid-palette-ref.tiff is a
  documented exception (the Deflate decoder resolves it);
- every in-scope valid file RESOLVES and its pixels equal Pillow's, except the open failures and the files whose pixel
  comparison belongs to format-coverage Task 38 (named below).

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


# format-coverage Requirement 18.6 and design.md: the 16 files the header rules leave out of scope.
STAYS_OUT = {
    "goimage_bw-gopher_ccittGroup3.tiff": "compression CCITT G3 (3)",
    "goimage_bw-gopher_ccittGroup4.tiff": "compression CCITT G4 (4)",
    "libtiff_testfax4.tiff": "compression CCITT G4 (4)",
    "pillow_hopper_g4.tif": "compression CCITT G4 (4)",
    "libtiff_ojpeg_zackthecat_subsamp22_single_strip.tiff": "compression OJPEG (6)",
    "pillow_old-style-jpeg-compression.tif": "compression OJPEG (6)",
    "libtiff_quad-tile.jpg.tiff": "compression JPEG (7)",
    "pillow_hopper_webp.tif": "compression WebP (50001)",
    "libtiff_logluv-3c-16b.tiff": "compression SGILog (34676)",
    "pillow_tiff_strip_planar_raw.tif": "planar configuration 2",
    "goimage_video-001-strip-64.tiff": "predictor 2",
    "goimage_video-001-tile-64x64.tiff": "predictor 2",
    "pillow_hopper_lzw.tif": "predictor 2",
    "pillow_tiff_adobe_deflate.tif": "predictor 2",
    "pillow_negative_size.ppm": "magic P6 not followed by a whitespace byte",
    OSSFUZZ: "PCX encoding byte 32",
}


def test_scope_counts():
    scopes = [scope_of(n) for n in FILES]
    assert scopes.count("in") == 65 and scopes.count("out") == 16
    assert len(rc.INVALID_BY_CONSTRUCTION) == 6
    assert {n for n in FILES if scope_of(n) == "out"} == set(STAYS_OUT)
    for name, reason in STAYS_OUT.items():
        assert MANIFEST[name]["scope_reason"] == reason, name


@pytest.mark.parametrize("name", FILES)
def test_committed_results_match_a_live_run(name):
    data, result = run(name)
    row = COMMITTED[name]
    assert row["our_status"] == result.status
    assert row["termination"] == getattr(result, "termination", None)
    assert row["checks"] == result.total_checks
    assert row["candidates"] == [rc.describe(c) for c in rc.candidates_of(result)]


# goimage_bw-deflate.tiff: the engine returns stored bytes; they equal Pillow's after WhiteIsZero inversion (tag 262 = 0).
# goimage_video-001-paletted.tiff: pixels equal Pillow's (mode P indices).
# goimage_invalid-palette-ref.tiff: decodes the same region as the paletted file; Pillow refuses it (UnidentifiedImageError).
BW_DEFLATE = "goimage_bw-deflate.tiff"
INVALID_PALETTE_REF = "goimage_invalid-palette-ref.tiff"
OUT_OF_SCOPE = [n for n in FILES if scope_of(n) == "out" and n != OSSFUZZ]


# In scope, valid, and FAILED: the two open failures, both listed in OPEN_IN_SCOPE_FAILURES (format-coverage Task 39).
# The first has a last strip that inflates past its rows (Principle call 2); the second is the RLE TGA whose footer
# overlaps its data (Requirement 5.9).
DEFLATE_EXTRA_DATA = "libtiff_deflate-last-strip-extra-data.tiff"


@pytest.mark.parametrize("name", [n for n in FILES if scope_of(n) == "in" and n not in rc.INVALID_BY_CONSTRUCTION
                                  and n not in (CROSS_SCAN, DEFLATE_EXTRA_DATA)])
def test_in_scope_valid_files_resolve(name):
    # Requirements 3.8, 4.1, 5.8, 6.2, 8.1, 9.1, 11.1, 12.1, 13.1, 14.1: every in-scope valid file resolves.
    assert run(name)[1].status == "RESOLVED"


def test_deflate_last_strip_extra_data_is_in_scope_and_failed():
    # Design.md row 25 (Principle call 2): in scope by its header, FAILED, an open failure (Requirement 19.4).
    assert scope_of(DEFLATE_EXTRA_DATA) == "in"
    result = run(DEFLATE_EXTRA_DATA)[1]
    assert result.status == "FAILED"
    assert any(r.reason == "decoder_overrun" and "inflates past 2000 bytes" in r.detail for r in result.rejections)


def test_tiff_lzma_file_resolves_with_pillows_pixels():
    # Requirement 14.1 to 14.3; format-coverage Task 26, design.md row 26. Pillow reads this file (RGB), so compare directly.
    Image = pytest.importorskip("PIL.Image")
    data, result = run("pillow_hopper_lzma.tif")
    assert result.status == "RESOLVED"
    im = Image.open(rc.REAL / "pillow_hopper_lzma.tif")
    assert im.mode == "RGB" and im.size == (128, 128)
    assert result.candidate.decoded == im.tobytes()


# format-coverage Task 28: the TIFF expectations the decoders made wrong. Before Tasks 18 to 26 every file below was
# FAILED (Requirement 20.4 replaces that expectation). Each file resolves under the stated encoding.
TIFF_ENCODING = {
    **{n: "none" for n in (                                                  # Requirements 8.1, 8.11, 9.1, 9.6
        "goimage_video-001-gray.tiff", "libtiff_minisblack-1c-8b.tiff", "libtiff_palette-1c-8b.tiff",
        "libtiff_rgb-3c-8b.tiff", "pillow_12bit.cropped.tif", "pillow_tiff_strip_raw.tif",
        "pillow_tiff_tiled_raw.tif")},
    "goimage_bw-packbits.tiff": "tiff_compression_32773",                    # Requirement 11.1
    "goimage_blue-purple-pink.lzwcompressed.tiff": "tiff_compression_5",     # Requirement 12.1
    "libtiff_lzw-single-strip.tiff": "tiff_compression_5",                   # Requirement 12.1, 12.8 (b)
    BW_DEFLATE: "tiff_compression_32946",                                    # Requirement 13.1
    "goimage_video-001-paletted.tiff": "tiff_compression_8",                 # Requirement 13.1
    INVALID_PALETTE_REF: "tiff_compression_8",                               # Requirement 13.1
    "pillow_hopper_lzma.tif": "tiff_compression_34925",                      # Requirement 14.1
}
TIFF_PREDICTOR_FAILED = [
    "goimage_video-001-strip-64.tiff", "goimage_video-001-tile-64x64.tiff", "pillow_hopper_lzw.tif",
    "pillow_tiff_adobe_deflate.tif",
]


def test_every_decoded_tiff_has_an_encoding_expectation():
    # The 14 TIFFs the format-coverage decoders newly resolve; each is in scope by the manifest.
    assert len(TIFF_ENCODING) == 14
    assert all(scope_of(n) == "in" for n in TIFF_ENCODING)


@pytest.mark.parametrize("name", sorted(TIFF_ENCODING))
def test_decoded_tiff_resolves_under_its_encoding(name):
    result = run(name)[1]
    assert result.status == "RESOLVED" and result.candidate.hypothesis.encoding == TIFF_ENCODING[name]
    assert result.candidate.hypothesis.probe_name == "tiff"


@pytest.mark.parametrize("name", TIFF_PREDICTOR_FAILED)
def test_predictor_tiffs_stay_failed_req_10_5(name):
    # Requirement 10.5: a declared Predictor other than 1 is refused for every compression; the file stays FAILED.
    _, result = run(name)
    assert scope_of(name) == "out" and MANIFEST[name]["scope_reason"] == "predictor 2"
    assert result.status == "FAILED" and result.termination == "exhausted"
    assert any("predictor (tag 317)" in r.detail for r in result.rejections)


@pytest.mark.parametrize("name", ["goimage_blue-purple-pink.lzwcompressed.tiff", "goimage_video-001-paletted.tiff"])
def test_decoded_compressed_tiff_bytes_equal_pillows(name):
    # Requirements 12.1 and 13.1. Pillow reads mode RGB or P at one byte per sample, so its bytes are the engine's.
    Image = pytest.importorskip("PIL.Image")
    result = run(name)[1]
    with Image.open(rc.REAL / name) as im:
        im.load()
        assert im.mode in ("RGB", "P")
        assert result.candidate.decoded == im.tobytes()


def test_decoded_packbits_bits_equal_pillows_pixels():
    # Requirement 11.1. The engine returns stored bits; Pillow inverts WhiteIsZero (tag 262 = 0) on load.
    Image = pytest.importorskip("PIL.Image")
    name = "goimage_bw-packbits.tiff"
    c = run(name)[1].candidate
    assert (c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth) == (153, 55, 1)
    with Image.open(rc.REAL / name) as im:
        im.load()
        invert = im.tag_v2.get(262) == 0
        for y in range(55):
            for x in range(153):
                stored = (c.decoded[y * c.row_stride + x // 8] >> (7 - x % 8)) & 1
                assert (1 - stored if invert else stored) == (1 if im.getpixel((x, y)) else 0), (x, y)


@pytest.mark.parametrize("name", OUT_OF_SCOPE)
def test_out_of_scope_is_a_stated_refusal(name):
    _, result = run(name)
    assert result.status == "FAILED", f"{name} returned {result.status}"
    assert result.termination in ("exhausted", "no_hypothesis_checked")


@pytest.mark.parametrize("name", [n for n in rc.INVALID_BY_CONSTRUCTION if n != OSSFUZZ])
def test_five_invalid_files_fail(name):
    if name == INVALID_PALETTE_REF:
        # Documented exception, format-coverage design.md row 25: the Deflate decoder resolves this file (it decodes the
        # same region as goimage_video-001-paletted.tiff). Pillow refuses it, which the committed row records.
        assert run(name)[1].status == "RESOLVED"
        assert COMMITTED[name]["pillow_decodes"] is False
        assert COMMITTED[name]["pillow_error"].startswith("UnidentifiedImageError")
        assert run(name)[1].candidate.decoded == run("goimage_video-001-paletted.tiff")[1].candidate.decoded
        return
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
# Pixel equality covers every in-scope valid file that resolves, except the one whose alpha reading differs
# (test_rgba16_differs_only_in_the_alpha_interpretation). The committed rows are regenerated by format-coverage Task 39.
# Four resolved files have a documented verdict instead of byte equality (format-coverage Task 38, Requirement 19.3):
# the engine's 16-bit and 12-bit scaling differs from Pillow's, and rgb32rle declares no alpha. Their verdict text is
# pinned below and each is a measured fact about Pillow's reading, not a skip.
DOCUMENTED_VERDICT = {
    "libtiff_rgb-3c-16b.ppm": "16-bit samples: engine v * 255 // maxval (Requirement 16.1)",
    "pillow_hopper_16bit.pgm": "16-bit samples: engine v * 255 // maxval (Requirement 16.1)",
    "pillow_12bit.cropped.tif": "12-bit samples: engine v * 255 // 4095 (Requirement 16.1)",
    "pillow_rgb32rle.tga": "alpha not compared: the file declares no alpha",
}
RECOVERABLE = [n for n in IN_SCOPE_VALID if n not in OPEN and n != RGBA16 and n not in DOCUMENTED_VERDICT]


def test_every_in_scope_valid_file_is_resolved_open_or_pinned_by_a_row():
    # 65 files in scope; four of the six invalid-by-construction files are among them (ossfuzz and negative_size are out).
    in_scope = [n for n in FILES if scope_of(n) == "in"]
    assert len(in_scope) == 65
    assert all(COMMITTED[n]["scope"] == "in" for n in in_scope)
    assert len(IN_SCOPE_VALID) == 61
    assert len(RECOVERABLE) == 54


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


@pytest.mark.parametrize("name", sorted(DOCUMENTED_VERDICT))
def test_documented_verdicts_are_committed_and_are_not_mismatches(name):
    verdicts = COMMITTED[name]["pixel_verdicts"]
    assert len(verdicts) == 1 and verdicts[0].startswith(DOCUMENTED_VERDICT[name])
    assert COMMITTED[name]["pillow_decodes"] is True and COMMITTED[name]["pillow_pixels_sha256"] is not None


def test_open_in_scope_failures_are_exactly_these():
    # format-coverage Requirement 19.4: two open failures, each with its measured note, each in scope and valid.
    assert OPEN == {CROSS_SCAN, DEFLATE_EXTRA_DATA}
    for name in OPEN:
        assert COMMITTED[name]["note"] == rc.NOTES[name]
        assert COMMITTED[name]["our_status"] == "FAILED" and COMMITTED[name]["scope"] == "in"
        assert name not in rc.INVALID_BY_CONSTRUCTION
        assert "invalid by construction" not in COMMITTED[name]["note"].lower()
    assert COMMITTED[CROSS_SCAN]["note"].startswith(
        "its RLE data needs one byte that lies inside its declared TGA 2.0 footer; "
        "Pillow decodes it because it ignores the footer")
    assert "inflates past 2000 bytes" in COMMITTED[DEFLATE_EXTRA_DATA]["note"]
    assert "Principle call 2" in COMMITTED[DEFLATE_EXTRA_DATA]["note"]


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


OPEN_REASON = {
    CROSS_SCAN: "in scope, valid, FAILED: its RLE data needs one byte inside its TGA 2.0 footer (Req 5.9)",
    DEFLATE_EXTRA_DATA: "in scope, valid, FAILED: its last strip inflates past its 2000 bytes (Principle call 2)",
}


@pytest.mark.parametrize("name", [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=OPEN_REASON[n]))
                                  for n in sorted(OPEN)])
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


BW_VERDICT = "stored bytes; equals Pillow after WhiteIsZero inversion (tag 262 = 0)"


def test_bw_deflate_verdict_is_recorded_as_a_documented_difference():
    # Design.md row 25. Tag 262 = 0 (WhiteIsZero): the engine returns stored bytes, Pillow inverts on load.
    assert COMMITTED[BW_DEFLATE]["pixel_verdicts"] == [BW_VERDICT]


@pytest.mark.skipif(not rc_has_pillow(), reason="Pillow not installed")
def test_bw_deflate_stored_bits_inverted_equal_pillows_pixels():
    # All 153 x 55 pixels; the padding bits of each 20-byte row (7 bits) are excluded. Requirement 13.1; design.md row 25.
    from PIL import Image
    data, result = run(BW_DEFLATE)
    c = result.candidate
    assert (c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth) == (153, 55, 1)
    with Image.open(rc.REAL / BW_DEFLATE) as im:
        im.load()
        assert im.mode == "1" and im.size == (153, 55)
        for y in range(55):
            for x in range(153):
                stored = (c.decoded[y * c.row_stride + x // 8] >> (7 - x % 8)) & 1
                assert (1 - stored) == (1 if im.getpixel((x, y)) else 0), (x, y)
