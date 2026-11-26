"""Emission of multi-plane PCX (format-coverage Task 29; Requirements 17.4, 17.8, 17.9).

The fixtures come from tests/test_pcx_planes.py, which builds them from the documented
PCX header layout (0x41 planes, 0x42 <H bytes_per_line).
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

from hypothesis import given, settings, strategies as st

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import extract_layout, make_parser_module, parse
from tests.test_pcx_planes import RGB_BODY, RGB_DECODED, pcx

# 5 x 1 pixels, 3 planes of 8 bits, bytes_per_line 6 (one pad byte per plane), no RLE.
# Scanline = plane 0 (6 bytes), plane 1 (6 bytes), plane 2 (6 bytes) = 18 bytes; the
# unpadded stride would be 15.
PADDED_BODY = bytes(range(1, 7)) + bytes(range(11, 17)) + bytes(range(21, 27))


def _emit(data):
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


def test_three_plane_layout_fields_req_17_4():
    data = pcx(1, 8, 3, 1, 3, 4, RGB_BODY)
    layout = build_layout(Engine().run(data), data)
    assert layout["kind"] == "format"
    assert layout["image"]["bit_depth"] == {"mul": ["bit_depth", "planes"]}
    assert layout["image"]["row_bytes"] == {"mul": ["planes", "bytes_per_line"]}


def test_requirements_state_planar_scanline_in_ears_req_17_4():
    _, files, _ = _emit(pcx(1, 8, 3, 1, 3, 4, RGB_BODY))
    req = files["requirements.md"]
    assert re.search(r"THE parser SHALL read each scanline as `planes` planes of "
                     r"`bytes_per_line` bytes, plane 0 first", req)


def test_reference_reader_reads_exact_planar_pixels_req_17_9():
    data = pcx(1, 8, 3, 1, 3, 4, RGB_BODY)
    _, files, _ = _emit(data)
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    assert (out["width"], out["height"], out["bit_depth"], out["row_stride"]) == (4, 2, 24, 12)
    assert out["pixels"] == RGB_DECODED


def test_reference_reader_honours_padded_planes_req_17_9():
    data = pcx(0, 8, 4, 0, 3, 6, PADDED_BODY)
    result, files, _ = _emit(data)
    assert result.status == "RESOLVED"
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    assert (out["width"], out["height"], out["row_stride"]) == (5, 1, 18)
    assert out["pixels"] == PADDED_BODY


def test_emitted_tests_pass_under_pytest_for_three_plane_pcx(tmp_path):  # Req 17.8
    _, files, slug = _emit(pcx(1, 8, 3, 1, 3, 4, RGB_BODY))
    module = slug.replace("-", "_")
    (tmp_path / ("parser_%s.py" % module)).write_bytes(
        make_parser_module(files["requirements.md"]).encode("utf-8"))
    (tmp_path / ("test_%s.py" % module)).write_bytes(files["test_%s.py" % module].encode("utf-8"))
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert re.search(r"(\d+) passed", out), out


def test_single_plane_pcx_emission_is_byte_for_byte_unchanged_req_17_4():
    # Hashes were taken from the emitter before Task 29 changed it.
    snap = json.loads((pathlib.Path(__file__).parent / "data"
                       / "pcx_single_plane_emit_sha256.json").read_text(encoding="ascii"))
    assert snap
    for name, want in snap.items():
        data = (SAMPLES_DIR / name).read_bytes()
        spec = emit_spec(Engine().run(data), data)
        got = {n: hashlib.sha256(t.encode("utf-8")).hexdigest() for n, t in spec.files}
        assert got == want, name


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=300))
def test_reference_reader_planar_layout_never_raises(b):
    data = pcx(1, 8, 3, 1, 3, 4, RGB_BODY)
    layout = extract_layout(_emit(data)[1]["requirements.md"])
    assert isinstance(parse(layout, b), dict)
