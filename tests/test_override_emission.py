"""Acceptance tests for overriding strategies in emission (Req 9.33, 9.34, Decision Record 27).
Expected values come from the requirements text. Inputs are corpus files and the
engine's own results; the crafted results change only the revision path.
"""
import dataclasses
import os
import re
import subprocess
import sys

import pytest

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import extract_layout, make_parser_module

_PATHS = {
    "external_a": SAMPLES_DIR / "external" / "external_a",
    "pillow_odd_stride.pcx": SAMPLES_DIR / "real" / "pillow_odd_stride.pcx",
}


def _bytes(name):
    return _PATHS.get(name, SAMPLES_DIR / name).read_bytes()


def _emit(name):
    data = _bytes(name)
    spec = emit_spec(Engine().run(data), data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return dict(spec.files), spec.slug


def _layout(name):
    files, _ = _emit(name)
    layout = extract_layout(files["requirements.md"])
    assert isinstance(layout, dict)
    return layout


def test_mystery_i_layout_is_file_with_note_and_override_statement():  # Req 9.33, 9.34
    layout = _layout("mystery_i")
    assert layout["kind"] == "file"
    note = layout.get("note", "")
    assert "describes this one file only, not the format" in note  # item 16 note
    assert "overridden" in note.lower()
    # this file's literal values
    assert layout["image"] == {"width": 8, "height": 8, "bit_depth": 8, "row_alignment": 1}
    assert layout["data"]["start"] == 128
    assert layout["data"]["encoding"] == "rle_pcx"


def test_mystery_i_requirements_state_no_format_wide_encoding_rule():  # Req 9.33
    req = _emit("mystery_i")[0]["requirements.md"]
    assert "overridden" in req.lower()
    assert "SHALL ignore it" not in req
    assert "WHEN the file's own encoding declaration" not in req


@pytest.mark.parametrize("name", ["mystery_b", "external_a", "pillow_odd_stride.pcx", "mystery_h"])
def test_other_pcx_layouts_stay_format(name):  # Req 9.34
    assert _layout(name)["kind"] == "format"


def _with_path(name, path):
    data = _bytes(name)
    result = Engine().run(data)
    cand = result.candidate
    hyp = dataclasses.replace(cand.hypothesis, revision_path=tuple(path))
    crafted = dataclasses.replace(result, candidate=dataclasses.replace(cand, hypothesis=hyp))
    return build_layout(crafted, data)


def test_crafted_path_of_recovered_conventions_stays_format():  # Req 9.33
    assert _with_path("mystery_b", ("inclusive_bounds", "row_padding_variants"))["kind"] == "format"


def test_crafted_path_containing_rle_pcx_is_file():  # Req 9.33
    layout = _with_path("mystery_b", ("inclusive_bounds", "rle_pcx"))
    assert layout["kind"] == "file"
    assert "overridden" in layout["note"].lower()


def test_mystery_i_emitted_suite_passes_with_reference_reader(tmp_path):  # Req 9.34, 9.31
    files, slug = _emit("mystery_i")
    test_name = "test_" + slug.replace("-", "_") + ".py"
    module_name = "parser_" + slug.replace("-", "_")
    (tmp_path / (module_name + ".py")).write_bytes(
        make_parser_module(files["requirements.md"]).encode("utf-8"))
    (tmp_path / test_name).write_bytes(files[test_name].encode("utf-8"))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    m = re.search(r"(\d+) passed", out)
    assert m and int(m.group(1)) >= 1, out
    assert "skipped" not in out, out
