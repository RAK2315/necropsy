"""Emission of rle_tga (format-coverage Task 30; Requirements 17.1, 17.2, 17.8, 17.9)."""
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

RLE_FILE = SAMPLES_DIR / "real" / "pillow_200x32_rgb_tl_rle.tga"


def _emit(data):
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


def test_mapping_sends_9_10_11_to_rle_tga_req_17_2():
    data = RLE_FILE.read_bytes()
    enc = build_layout(Engine().run(data), data)["data"]["encoding"]
    assert enc["field"] == "image_type"
    assert enc["values"] == {"1": "none", "2": "none", "3": "none",
                             "9": "rle_tga", "10": "rle_tga", "11": "rle_tga"}
    assert enc["otherwise"] == "unsupported"


def test_requirements_define_rle_tga_in_ears_req_17_1():
    _, files, _ = _emit(RLE_FILE.read_bytes())
    req = files["requirements.md"]
    assert "WHEN the encoding is `rle_tga`, THE parser SHALL" in req
    assert "WHEN the encoding is `unsupported`, THE parser SHALL" in req


def test_reference_reader_reads_exact_rle_pixels_req_17_9():
    data = RLE_FILE.read_bytes()
    result, files, _ = _emit(data)
    assert result.status == "RESOLVED" and result.candidate.hypothesis.encoding == "rle_tga"
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    assert (out["width"], out["height"], out["bit_depth"]) == (200, 32, 24)
    assert out["encoding"] == "rle_tga"
    assert out["pixels"] == result.candidate.decoded
    assert len(out["pixels"]) == 200 * 32 * 3


def test_emitted_tests_pass_under_pytest_for_rle_tga(tmp_path):  # Req 17.8
    _, files, slug = _emit(RLE_FILE.read_bytes())
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


def _undo_17_2(name, text):
    """Reverse the one change Requirement 17.2 makes to a TGA requirements.md."""
    if name != "requirements.md":
        return text
    text = re.sub(r'("(?:9|10|11)": )"rle_tga"', r'\1"unsupported"', text)
    text = re.sub(r"(?<=, )(9|10|11) \u2192 `rle_tga`", "\\1 \u2192 `unsupported`", text)
    lines = [ln for ln in text.split("\n") if not re.match(r"\d+\. WHEN the encoding is `rle_tga`", ln)]
    return "\n".join(lines).replace("14. WHEN the encoding is `unsupported`",
                                    "13. WHEN the encoding is `unsupported`")


def test_other_tga_emission_unchanged_except_req_17_2():
    # Hashes were taken from the emitter before Task 30 changed it. Only the mapping
    # and the rle_tga definition (Requirement 17.2) may differ, in requirements.md.
    snap = json.loads((pathlib.Path(__file__).parent / "data"
                       / "tga_pre_rle_emit_sha256.json").read_text(encoding="ascii"))
    assert len(snap) >= 10
    for name, want in snap.items():
        base = SAMPLES_DIR / name if (SAMPLES_DIR / name).exists() else SAMPLES_DIR / "real" / name
        data = base.read_bytes()
        spec = emit_spec(Engine().run(data), data)
        got = {n: hashlib.sha256(_undo_17_2(n, t).encode("utf-8")).hexdigest() for n, t in spec.files}
        assert got == want, name


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=400), st.booleans())
def test_reference_reader_rle_tga_never_raises(body, keep_header):
    raw = RLE_FILE.read_bytes()
    layout = extract_layout(_emit(raw)[1]["requirements.md"])
    data = raw[:18] + body if keep_header else body
    assert isinstance(parse(layout, data), dict)
