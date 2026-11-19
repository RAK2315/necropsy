"""Acceptance tests for spec emission (Req 9.16, 9.17, 9.18).

The reference reader is given only the emitted requirements.md text. The original
corpus bytes are the input being parsed, and the engine result is the check.
"""
import os
import subprocess
import sys

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.support.reference_reader import (
    extract_layout, make_parser_module, parse, parse_candidates,
)


def _emit(name):
    data = corpus_bytes(name)
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


def _read_with_markdown_only(markdown, file_bytes):
    """Reference reading: format knowledge comes only from `markdown`."""
    layout = extract_layout(markdown)
    assert isinstance(layout, dict), layout
    return parse(layout, file_bytes)


def _candidates_with_markdown_only(markdown, file_bytes):
    layout = extract_layout(markdown)
    assert isinstance(layout, dict), layout
    return parse_candidates(layout, file_bytes)


def test_mystery_e_reference_reader_reproduces_layout():  # Req 9.16
    result, files, _ = _emit("mystery_e")
    out = _read_with_markdown_only(files["requirements.md"], corpus_bytes("mystery_e"))
    assert out["ok"] is True, out
    assert (out["width"], out["height"], out["bit_depth"]) == (8, 8, 8)
    assert (out["data_start"], out["data_end"]) == (86, 150)
    assert out["pixels"] == result.candidate.decoded
    assert len(out["pixels"]) == 64


@pytest.mark.parametrize("name", ["mystery_c", "mystery_e"])
def test_emitted_tests_pass_under_pytest(name, tmp_path):  # Req 9.17
    _, files, slug = _emit(name)
    module_src = make_parser_module(files["requirements.md"])
    tests_src = files["tests.py"]
    assert "necropsy" not in module_src.replace("necropsy-layout", "")
    assert "import necropsy" not in tests_src and "from necropsy" not in tests_src

    module_name = "parser_" + slug.replace("-", "_")
    (tmp_path / (module_name + ".py")).write_bytes(module_src.encode("utf-8"))
    (tmp_path / "tests.py").write_bytes(tests_src.encode("utf-8"))

    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "tests.py"), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_mystery_d_candidates_include_true_layout():  # Req 9.18
    _, files, _ = _emit("mystery_d")
    outs = _candidates_with_markdown_only(files["requirements.md"], corpus_bytes("mystery_d"))
    assert any(
        o.get("ok") and (o["width"], o["height"], o["bit_depth"], o["data_start"]) == (8, 8, 8, 40)
        for o in outs
    ), outs
