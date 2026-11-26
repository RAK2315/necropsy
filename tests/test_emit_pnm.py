"""Emission of PNM layouts (format-coverage Task 32; Requirements 17.1, 17.5, 17.8, 17.9)."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import extract_layout, make_parser_module, parse

REAL = SAMPLES_DIR / "real"
P5 = REAL / "imagemagick_input_p5.pgm"
P6 = REAL / "imagemagick_input_p6.ppm"
P3 = REAL / "imagemagick_input_p3.ppm"
P2 = REAL / "imagemagick_input_p2.pgm"
P1 = REAL / "imagemagick_input_p1.pbm"
P16 = REAL / "pillow_hopper_16bit.pgm"
PNM_FILES = [P5, P6, P3, P2, P1, P16]


def _emit(data):
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


@pytest.mark.parametrize("path", PNM_FILES, ids=lambda p: p.name)
def test_pnm_layout_is_file_kind_with_literals_req_17_5(path):
    data = path.read_bytes()
    result = Engine().run(data)
    assert result.status == "RESOLVED" and result.candidate.hypothesis.probe_name == "pnm"
    h = result.candidate.hypothesis
    lay = build_layout(result, data)
    assert lay["kind"] == "file"
    names = [f["name"] for f in lay["fields"]]
    assert names[:3] == ["magic", "width", "height"]
    assert ("maxval" in names) == (not data.startswith(b"P1"))
    assert all(f["expect"] is None for f in lay["fields"])
    assert lay["image"] == {"width": h.width, "height": h.height, "bit_depth": h.bit_depth,
                            "row_alignment": h.row_alignment, "maxval": h.maxval}
    assert lay["data"]["start"] == h.header_size and lay["data"]["end"] is None
    assert lay["data"]["trailers"] == []
    assert lay["data"]["encoding"] == ("pnm_text" if data[1:2] in (b"1", b"2", b"3") else "none")


def test_document_states_header_grammar_and_defines_pnm_text_req_17_5_17_1():
    _, files, _ = _emit(P3.read_bytes())
    req = files["requirements.md"]
    assert "first 1,024 bytes" in req and "a comment" in req
    assert "WHEN the encoding is `pnm_text`, THE parser SHALL" in req
    assert "maximum sample value as 255" in req
    _, files5, _ = _emit(P5.read_bytes())
    assert "WHEN the encoding is `pnm_text`" not in files5["requirements.md"]
    assert "exactly one whitespace byte" in files5["requirements.md"]


@pytest.mark.parametrize("path", PNM_FILES, ids=lambda p: p.name)
def test_reference_reader_reads_exact_pnm_pixels_req_17_9(path):
    data = path.read_bytes()
    result, files, _ = _emit(data)
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    c = result.candidate
    assert (out["width"], out["height"], out["bit_depth"]) == (
        c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth)
    assert (out["data_start"], out["data_end"]) == (c.data_start, c.data_end)
    assert out["pixels"] == c.decoded


def test_reference_reader_refuses_sample_above_maxval_req_17_5():
    data = bytearray(b"P5\n2 2\n9\n" + bytes([0, 1, 2, 3]))
    layout = extract_layout(_emit(bytes(data))[1]["requirements.md"])
    assert parse(layout, bytes(data))["ok"] is True
    data[-1] = 10   # one sample above the declared maximum 9
    out = parse(layout, bytes(data))
    assert out["ok"] is False and "maximum" in out["error"]


def test_reference_reader_pnm_text_ends_are_errors():
    layout = extract_layout(_emit(b"P2\n2 1\n255\n1 2\n")[1]["requirements.md"])
    assert parse(layout, b"P2\n2 1\n255\n1 2\n")["pixels"] == b"\x01\x02"
    assert parse(layout, b"P2\n2 1\n255\n1 2 # c\n \n")["ok"] is True
    for bad in (b"P2\n2 1\n255\n1\n", b"P2\n2 1\n255\n1 2 3\n", b"P2\n2 1\n255\n1 256\n",
                b"P2\n2 1\n255\n1 x\n", b"P2\n2 1\n255\n12\n"):
        assert parse(layout, bad)["ok"] is False, bad


@pytest.mark.parametrize("path", [P5, P6, P3], ids=lambda p: p.name)
def test_emitted_tests_pass_under_pytest_for_pnm(tmp_path, path):  # Req 17.7, 17.8, 17.9
    _, files, slug = _emit(path.read_bytes())
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
    assert "skipped" not in out, out


def test_non_pnm_emission_unchanged():
    # Hashes were taken from the emitter before Task 32 changed it: every sample whose
    # result holds no PNM candidate must emit byte for byte what it did.
    snap = json.loads((pathlib.Path(__file__).parent / "data"
                       / "non_pnm_emit_sha256.json").read_text(encoding="ascii"))
    assert len(snap) >= 50
    tiff_pinned = json.loads((pathlib.Path(__file__).parent / "data"
                              / "tiff_pre_t33_emit_sha256.json").read_text(encoding="ascii"))
    for name, want in snap.items():
        if name in tiff_pinned:
            # Requirement 17.3 (Task 33) changes every TIFF requirements.md; those emissions are
            # pinned, with that change undone, in tests/test_emit_tiff.py.
            continue
        data = (SAMPLES_DIR / name).read_bytes()
        spec = emit_spec(Engine().run(data), data)
        got = {n: hashlib.sha256(t.encode("utf-8")).hexdigest() for n, t in sorted(spec.files)}
        assert got == want, name


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=400), st.booleans(), st.sampled_from([P5, P6, P3, P2, P1, P16]))
def test_reference_reader_pnm_never_raises(body, keep_header, path):
    raw = path.read_bytes()
    layout = extract_layout(_emit(raw)[1]["requirements.md"])
    data = raw[:12] + body if keep_header else body
    assert isinstance(parse(layout, data), dict)
