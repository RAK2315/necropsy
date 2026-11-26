"""Acceptance tests for encoding definitions in emitted specs (Req 9.28 to 9.32, Decision Record 26).

Expected values come from the requirements text. Inputs are corpus files and the
engine's own results.
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import make_parser_module

_PATHS = {
    "external_a": SAMPLES_DIR / "external" / "external_a",
}


def _bytes(name):
    path = _PATHS.get(name, SAMPLES_DIR / name)
    return path.read_bytes()


def _emit(name):
    data = _bytes(name)
    spec = emit_spec(Engine().run(data), data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return dict(spec.files), spec.slug


def _write_suite(tmp_path, files, slug, module_src):
    test_name = "test_" + slug.replace("-", "_") + ".py"
    assert test_name in files, sorted(files)
    module_name = "parser_" + slug.replace("-", "_")
    (tmp_path / (module_name + ".py")).write_bytes(module_src.encode("utf-8"))
    (tmp_path / test_name).write_bytes(files[test_name].encode("utf-8"))


def _run_pytest(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=600,
    )
    return proc.returncode, proc.stdout + proc.stderr


_DO_NOTHING = '''"""Do-nothing parser (Req 9.32)."""


def parse(data):
    return {"ok": False, "error": "encoding rle_pcx not supported"}


def parse_candidates(data):
    return [{"ok": False, "error": "encoding rle_pcx not supported"}]
'''


@pytest.mark.parametrize("name", ["mystery_b", "mystery_i", "external_a"])
def test_do_nothing_parser_fails_emitted_suite(name, tmp_path):  # Req 9.32
    files, slug = _emit(name)
    _write_suite(tmp_path, files, slug, _DO_NOTHING)
    code, out = _run_pytest(tmp_path)
    assert code != 0, out
    m = re.search(r"(\d+) failed", out)
    assert m and int(m.group(1)) >= 1, out
    assert "skipped" not in out, out


@pytest.mark.parametrize(
    "name", ["mystery_b", "mystery_i", "external_a", "mystery_c", "mystery_e"])
def test_reference_reader_passes_emitted_suite_without_skips(name, tmp_path):  # Req 9.30, 9.31
    files, slug = _emit(name)
    _write_suite(tmp_path, files, slug, make_parser_module(files["requirements.md"]))
    code, out = _run_pytest(tmp_path)
    assert code == 0, out
    m = re.search(r"(\d+) passed", out)
    assert m and int(m.group(1)) >= 1, out
    assert "skipped" not in out, out


def test_mystery_b_requirements_define_rle_pcx_only():  # Req 9.28
    files, _ = _emit("mystery_b")
    req = files["requirements.md"]
    assert "0xC0" in req
    assert "& 0x3F" in req
    assert re.search(r"last byte", req)
    assert re.search(r"exceed", req)
    assert re.search(r"shorter than", req)
    assert re.search(r"unread", req)
    assert re.search(r"literal", req, re.I)
    # One definition line per encoding name, each an EARS sentence naming the encoding.
    rle_lines = [l for l in req.splitlines()
                 if "`rle_pcx`" in l and "SHALL" in l and "selected by the value" not in l]
    assert rle_lines, "no rle_pcx definition"
    assert "unsupported" not in req


def test_mystery_c_requirements_define_unsupported():  # Req 9.28
    files, _ = _emit("mystery_c")
    req = files["requirements.md"]
    unsup = [l for l in req.splitlines()
             if "`unsupported`" in l and "SHALL" in l and "selected by the value" not in l]
    assert unsup, "no unsupported definition"


def test_mystery_c_requirements_name_rle_tga_for_9_10_11_and_none_for_1_2_3():
    # Requirement 17.2 replaces engine Requirement 9.29 for image types 9, 10, 11:
    # the engine decodes rle_tga, so the emitted spec names and defines it.
    files, _ = _emit("mystery_c")
    req = files["requirements.md"]
    assert "WHEN the encoding is `rle_tga`, THE parser SHALL" in req
    for t in ("9", "10", "11"):
        assert f"{t} \u2192 `rle_tga`" in req, t
        assert f'"{t}": "rle_tga"' in req, t
        assert f"{t} \u2192 `unsupported`" not in req, t
    for t in ("1", "2", "3"):
        assert f"{t} \u2192 `none`" in req, t
        assert f'"{t}": "none"' in req, t


# ---- additions for the items 21.1 did not cover (Req 9.28 to 9.31) ----
from tests.support import reference_reader as rr


def _all_sample_paths():
    paths = sorted(p for p in SAMPLES_DIR.glob("mystery_*") if p.is_file())
    paths += sorted(p for p in (SAMPLES_DIR / "external").glob("external_*") if p.is_file())
    paths += sorted(p for p in (SAMPLES_DIR / "real").iterdir()
                    if p.is_file() and p.suffix.lower() in
                    (".pcx", ".tga", ".tif", ".tiff", ".pbm", ".pgm", ".ppm", ".pnm"))
    return paths


def test_emitted_test_text_has_no_encoding_skip_or_refused():  # Req 9.30
    for name in ("mystery_b", "mystery_c", "mystery_i", "external_a"):
        files, slug = _emit(name)
        text = files["test_" + slug.replace("-", "_") + ".py"]
        assert 'pytest.skip("encoding' not in text, name
        assert "refused" not in text, name
        assert "pixels_sha256" in text, name


def test_rle_tga_specs_name_define_and_decode_rle_tga():  # Req 17.2 (replaces engine Req 9.29), 20.4
    checked = 0
    for path in _all_sample_paths():
        data = path.read_bytes()
        result = Engine().run(data)
        spec = emit_spec(result, data)
        if hasattr(spec, "message"):
            continue  # not RESOLVED or AMBIGUOUS: no spec emitted
        files = dict(spec.files)
        req = files["requirements.md"]
        if "image_type" not in req:
            # Not a TGA spec: rle_tga is only named through the TGA image_type mapping.
            for fname, text in files.items():
                assert "rle_tga" not in text, (path.name, fname)
            continue
        checked += 1
        for t in ("9", "10", "11"):
            assert f'"{t}": "rle_tga"' in req, (path.name, t)
            assert f"{t} \u2192 `rle_tga`" in req, (path.name, t)
        for t in ("1", "2", "3"):
            assert f'"{t}": "none"' in req, (path.name, t)
            assert f"{t} \u2192 `none`" in req, (path.name, t)
        assert re.search(r"^\d+\. WHEN the encoding is `rle_tga`, THE parser SHALL", req, re.M), path.name
        text = files["test_" + spec.slug.replace("-", "_") + ".py"]
        assert 'pytest.skip("encoding' not in text, path.name
        assert "refused" not in text, path.name
        cand = getattr(result, "candidate", None)
        if cand is not None:
            assert hashlib.sha256(cand.decoded).hexdigest() in text, path.name
    assert checked >= 5


def _layout(width, height):
    return {"schema": "necropsy-layout/1", "kind": "file", "slug": "x",
            "fields": [],
            "image": {"width": width, "height": height, "bit_depth": 8, "row_alignment": 1},
            "data": {"start": 0, "end": None, "trailers": [], "encoding": "rle_pcx"}}


@pytest.mark.parametrize("region,w,h,pixels", [
    (b"\xC3\x07", 3, 1, b"\x07\x07\x07"),                    # one run
    (b"\x01\x02\x03", 3, 1, b"\x01\x02\x03"),                # literals
    (b"\xC0\x09\x05", 1, 1, b"\x05"),                        # run count 0 allowed
    (b"\x01\xC2\x09", 3, 1, b"\x01\x09\x09"),                # literal then run
    (b"\xC1\xC5", 1, 1, b"\xC5"),                            # run of 1 of 0xC5
])
def test_reference_reader_rle_pcx_ok(region, w, h, pixels):  # Req 9.28
    r = rr.parse(_layout(w, h), region)
    assert r["ok"], r
    assert r["pixels"] == pixels


@pytest.mark.parametrize("region,w,h", [
    (b"\x01\xC2", 3, 1),                # marker as last byte
    (b"\xC5\x07", 3, 1),                # run exceeds expected output
    (b"\x01\x02", 3, 1),                # short output
    (b"\x01\x02\x03\x04", 3, 1),        # unread bytes
])
def test_reference_reader_rle_pcx_errors(region, w, h):  # Req 9.28
    r = rr.parse(_layout(w, h), region)
    assert r["ok"] is False and r["error"], r
    assert "not supported" not in r["error"], r


def test_reference_reader_unsupported_names_declared_value():  # Req 9.28
    lay = _layout(1, 1)
    lay["data"]["encoding"] = {"field": "t", "values": {"1": "none"}, "otherwise": "unsupported"}
    lay["fields"] = [{"name": "t", "offset": 0, "fmt": "<B", "expect": None}]
    r = rr.parse(lay, b"\x0A\x00")
    assert r["ok"] is False and "10" in r["error"], r


def test_reference_reader_imports_nothing_from_necropsy():  # Req 9.28
    src = open(rr.__file__, encoding="utf-8").read()
    assert not re.search(r"^\s*(from|import)\s+necropsy", src, re.M)
    imports = set(re.findall(r"^\s*(?:from|import)\s+(\w+)", src, re.M))
    assert imports <= {"json", "re", "struct"}, imports