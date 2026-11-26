"""Emitted tests of the new layouts (format-coverage Task 36; Requirements 17.7, 17.9, 17.10).

One file per new layout: a P5, a P6, a P2, a P3, an RLE TGA, a 3-plane PCX (built from the
documented header in tests/test_pcx_planes.py), a multi-strip TIFF, a tiled TIFF, and a PackBits,
an LZW, a Deflate and the LZMA TIFF.

* The emitted test_<module>.py, with the reference reader as parser_<module>, passes plain
  pytest and nothing is skipped except the source-too-large skip (engine Requirement 9.12).
* A do-nothing parser fails that file (Requirement 17.10). Where the source is over the embed
  limit the emitted file cannot hold it, so the reference reader is compared with the engine's
  own decode directly instead.
"""
import os
import re
import subprocess
import sys

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import extract_layout, make_parser_module, parse
from tests.test_pcx_planes import RGB_BODY, pcx

REAL = SAMPLES_DIR / "real"
MAX_EMBED = 65536

FILES = {
    "p5": "imagemagick_input_p5.pgm",
    "p6": "imagemagick_input_p6.ppm",
    "p2": "imagemagick_input_p2.pgm",
    "p3": "imagemagick_input_p3.ppm",
    "rle_tga": "pillow_200x32_rgb_tl_rle.tga",
    "multi_strip": "pillow_tiff_strip_raw.tif",
    "tiled": "pillow_tiff_tiled_raw.tif",
    "packbits": "goimage_bw-packbits.tiff",
    # pillow_hopper_lzw.tif declares Predictor 2 and is refused (Requirement 10), so it is not used.
    "lzw_single_strip": "libtiff_lzw-single-strip.tiff",  # 76,264 bytes: over the embed limit
    "lzw_strips": "goimage_blue-purple-pink.lzwcompressed.tiff",
    "deflate": "goimage_bw-deflate.tiff",
    "lzma": "pillow_hopper_lzma.tif",
}


def _source(case):
    if case == "three_plane_pcx":
        return pcx(1, 8, 3, 1, 3, 4, RGB_BODY)
    return (REAL / FILES[case]).read_bytes()


CASES = list(FILES) + ["three_plane_pcx"]

_DO_NOTHING = '''"""Do-nothing parser (Requirement 17.10)."""


def parse(data):
    return {"ok": False, "error": "encoding not supported"}


def parse_candidates(data):
    return [{"ok": False, "error": "encoding not supported"}]
'''


def _emit(case):
    data = _source(case)
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return data, result, dict(spec.files), spec.slug


def _suite(tmp_path, files, slug, module_src):
    module = slug.replace("-", "_")
    (tmp_path / ("parser_%s.py" % module)).write_bytes(module_src.encode("utf-8"))
    (tmp_path / ("test_%s.py" % module)).write_bytes(files["test_%s.py" % module].encode("utf-8"))
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=540)
    return proc.returncode, proc.stdout + proc.stderr


@pytest.mark.parametrize("case", CASES)
def test_emitted_test_text_has_no_refused_clause_and_only_the_size_skip(case):  # Req 17.7
    data, _, files, slug = _emit(case)
    text = files["test_%s.py" % slug.replace("-", "_")]
    assert "refused" not in text
    assert 'pytest.skip("encoding' not in text
    assert "pixels_sha256" in text
    skips = re.findall(r"pytest\.skip\(([^)]*)\)", text)
    assert skips == ['"source larger than 65,536 bytes; fixture not embedded"']
    assert ("SOURCE = None" in text) == (len(data) > MAX_EMBED)


@pytest.mark.parametrize("case", CASES)
def test_reference_reader_equals_the_engine_directly_req_17_7(case):
    data, result, files, _ = _emit(case)
    assert result.status == "RESOLVED", (case, result.status)
    cand = result.candidate
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    h = cand.hypothesis
    assert (out["width"], out["height"], out["bit_depth"], out["row_alignment"]) == (
        h.width, h.height, h.bit_depth, h.row_alignment)
    assert (out["data_start"], out["data_end"]) == (cand.data_start, cand.data_end)
    assert out["pixels"] == cand.decoded


@pytest.mark.parametrize("case", CASES)
def test_emitted_suite_passes_plain_pytest_with_the_reference_reader_req_17_9(case, tmp_path):
    data, _, files, slug = _emit(case)
    code, out = _suite(tmp_path, files, slug, make_parser_module(files["requirements.md"]))
    assert code == 0, out
    assert re.search(r"(\d+) passed", out), out
    skipped = re.search(r"(\d+) skipped", out)
    if len(data) <= MAX_EMBED:
        assert skipped is None, out
    else:
        assert skipped and int(skipped.group(1)) == 1, out


@pytest.mark.parametrize("case", [c for c in CASES if len(_source(c)) <= MAX_EMBED])
def test_do_nothing_parser_fails_the_emitted_suite_req_17_10(case, tmp_path):
    _, _, files, slug = _emit(case)
    code, out = _suite(tmp_path, files, slug, _DO_NOTHING)
    assert code != 0, out
    m = re.search(r"(\d+) failed", out)
    assert m and int(m.group(1)) >= 1, out
    assert "skipped" not in out, out
