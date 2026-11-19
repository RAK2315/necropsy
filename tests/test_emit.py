"""Unit tests for spec emission (task 11.7).

Expected values come from requirements.md (Requirement 9, 11.7) and design.md
("Spec emission", "Corpus Trace"), not from the implementation.
"""
import ast
import dataclasses
import fnmatch
import hashlib
import json
import re
from pathlib import Path

import pytest

from necropsy.emit import EmitError, EmittedSpec, emit_spec, write_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine, RejectionEntry
from tests.conftest import CORPUS_NAMES, corpus_bytes
from tests.support.reference_reader import extract_layout

PYTEST_CONFIG_FILES = ("pytest.ini", "setup.cfg", "tox.ini", "pyproject.toml", "conftest.py")


def emitted_test_name(slug):
    """Req 9.1: test_<module>.py, <module> being the slug with '-' replaced by '_'."""
    return "test_" + slug.replace("-", "_") + ".py"


def expected_files(slug):
    return ("requirements.md", "design.md", emitted_test_name(slug))


BLOCK_RE = re.compile(r"^```necropsy-layout[ \t]*\r?\n", re.M)


def _emit(name):
    data = corpus_bytes(name)
    result = Engine().run(data)
    spec = emit_spec(result, data)
    return data, result, spec


def _file(spec, name):
    return dict(spec.files)[name]


def _layout(name):
    spec = _emit(name)[2]
    assert isinstance(spec, EmittedSpec)
    layout = extract_layout(_file(spec, "requirements.md"))
    assert isinstance(layout, dict)
    return layout


# --- Slugs (Req 9.2) ---------------------------------------------------------

@pytest.mark.parametrize("name,slug", [("mystery_e", "tiff"), ("mystery_b", "pcx"),
                                       ("mystery_a", "pbm")])
def test_probe_slug_is_probe_name(name, slug):
    # Req 9.2
    assert _emit(name)[2].slug == slug


def test_generic_slug_is_unknown_plus_sha256_prefix():
    # Req 9.2
    data, _, spec = _emit("mystery_d")
    assert spec.slug == "unknown-" + hashlib.sha256(data).hexdigest()[:8]


# --- Files and layout block (Req 9.1, 9.6) -----------------------------------

@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_exactly_three_files_one_layout_block(name):
    # Req 9.1, 9.6
    spec = _emit(name)[2]
    assert isinstance(spec, EmittedSpec)
    assert tuple(n for n, _ in spec.files) == expected_files(spec.slug)
    assert len(spec.files) == 3
    req = _file(spec, "requirements.md")
    assert len(BLOCK_RE.findall(req)) == 1
    layout = extract_layout(req)
    assert isinstance(layout, dict)
    assert layout["schema"] == "necropsy-layout/1"


# --- Layout kinds (Req 9.7-9.9) ----------------------------------------------

def test_tiff_layout_is_format_with_byte_order_and_tag_table():
    # Req 9.7
    layout = _layout("mystery_e")
    assert layout["kind"] == "format"
    assert layout["byte_order"]
    assert layout["tag_table"]


def test_pbm_layout_is_file():
    # Req 9.7 (PBM text header: kind file)
    assert _layout("mystery_a")["kind"] == "file"


def test_generic_layout_is_file_kind_in_candidates_and_ambiguous_overall():
    # Req 9.9; design.md corpus trace: mystery_d has 18 candidates
    layout = _layout("mystery_d")
    assert layout["kind"] == "ambiguous"
    assert len(layout["candidates"]) == 18
    # design.md: ambiguous kind sets only schema, kind, slug, candidates
    assert set(layout) == {"schema", "kind", "slug", "candidates"}
    for cand in layout["candidates"]:
        assert cand["kind"] == "file"  # Req 9.8


def test_build_layout_matches_emitted_block():
    data = corpus_bytes("mystery_e")
    result = Engine().run(data)
    built = build_layout(result, data)
    assert built["kind"] == "format"
    assert built["schema"] == "necropsy-layout/1"
    assert json.loads(json.dumps(built)) == built


def test_pcx_inclusive_bounds_width_expression():
    # design.md per-origin table (PCX, inclusive_bounds in path)
    layout = _layout("mystery_b")
    assert layout["image"]["width"] == {"add": [{"sub": ["xmax", "xmin"]}, 1]}
    assert layout["image"]["height"] == {"add": [{"sub": ["ymax", "ymin"]}, 1]}


# --- Prose statements ---------------------------------------------------------

def test_mystery_i_states_encoding_declaration_overridden():
    # Req 9.7
    spec = _emit("mystery_i")[2]
    assert "overridden" in _file(spec, "requirements.md").lower()
    assert _layout("mystery_i")["data"]["encoding"] == "rle_pcx"


def test_ambiguous_requirements_state_candidates_and_failure_modes():
    # Req 9.9, 11.7
    spec = _emit("mystery_d")[2]
    req = _file(spec, "requirements.md")
    low = req.lower()
    for k in range(1, 19):
        assert re.search(r"candidate %d\b" % k, low), k
    assert re.search(r"pass(es)? (the )?closure", low)
    assert "cannot separate" in low
    assert "heuristic" in low
    # three failure modes (Req 11.7)
    assert "narrower" in low
    assert "identical bytes" in low
    assert "absorb" in low
    # asserts no single candidate: layout has no top-level fields/image
    layout = extract_layout(req)
    assert "fields" not in layout and "image" not in layout


def test_generic_spec_states_one_file_not_a_format():
    # Req 9.8
    low = _file(_emit("mystery_d")[2], "requirements.md").lower()
    assert "one file's layout" in low or "this file's layout" in low
    assert re.search(r"not (a|describe a) format|does not describe a format", low)


# --- design.md (Req 9.10, 8.4) -----------------------------------------------

def test_design_has_closure_line_for_mystery_e():
    # Req 8.4 via 9.10
    design = _file(_emit("mystery_e")[2], "design.md")
    assert "closure: [86, 150) holds 64 bytes = 8 x 8" in design


def test_design_lists_at_most_500_rejections():
    # Req 9.10: first 500 listed, remainder counted
    data = corpus_bytes("mystery_d")
    result = Engine().run(data)
    # mystery_d records no rejections, so supply 600 synthetic ones.
    extra = tuple(RejectionEntry("arithmetic_mismatch", "generic", None, k)
                  for k in range(600))
    big = dataclasses.replace(result, rejections=extra)
    n = len(extra)
    design = _file(emit_spec(big, data), "design.md")
    assert "… and %d more not listed" % (n - 500) in design
    reasons = ("arithmetic_mismatch|decoder_overrun|decoder_underrun|decoder_unconsumed|"
               "degenerate_hypothesis|field_out_of_bounds|probe_precondition_failed|"
               "unsupported_encoding")
    listed = [ln for ln in design.splitlines()
              if re.match(r"\s*\d+\.", ln) and re.search(reasons, ln)]
    assert len(listed) == 500


# --- test_<module>.py (Req 9.1, 9.11) -----------------------------------------

@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_generated_tests_compile(name):
    # Req 9.11
    spec = _emit(name)[2]
    assert isinstance(spec, EmittedSpec)
    fname = emitted_test_name(spec.slug)
    compile(_file(spec, fname), fname, "exec")


@pytest.mark.parametrize("name,fname", [("mystery_e", "test_tiff.py"),
                                        ("mystery_b", "test_pcx.py"),
                                        ("mystery_a", "test_pbm.py")])
def test_test_file_name_for_probe_slugs(name, fname):
    # Req 9.1
    assert [n for n, _ in _emit(name)[2].files][2] == fname


def test_test_file_name_for_generic_slug():
    # Req 9.1: test_unknown_<8 hex>.py
    data, _, spec = _emit("mystery_d")
    digest = hashlib.sha256(data).hexdigest()[:8]
    assert [n for n, _ in spec.files][2] == "test_unknown_" + digest + ".py"


@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_test_file_name_matches_pytest_default_and_no_config_file(name):
    # Req 9.1: collected by default; no pytest configuration file emitted
    spec = _emit(name)[2]
    assert isinstance(spec, EmittedSpec)
    names = [n for n, _ in spec.files]
    assert fnmatch.fnmatch(names[2], "test_*.py")
    assert not set(names) & set(PYTEST_CONFIG_FILES)


# --- FailureReport (Req 9.13) -------------------------------------------------

def test_failure_report_gives_emit_error(tmp_path):
    # Req 9.13
    data = b"\x00"
    result = Engine().run(data)
    assert result.status == "FAILED"
    out = emit_spec(result, data)
    assert isinstance(out, EmitError)
    assert list(tmp_path.iterdir()) == []


# --- write_spec (Req 9.15) ----------------------------------------------------

def test_write_spec_writes_only_three_files_without_bom(tmp_path):
    # Req 9.15
    spec = _emit("mystery_e")[2]
    out = tmp_path / "out"
    out.mkdir()
    folder = write_spec(spec, out)
    assert not isinstance(folder, EmitError)
    assert Path(folder) == out / "tiff"
    assert sorted(p.name for p in Path(folder).iterdir()) == sorted(
        ["requirements.md", "design.md", "test_tiff.py"])
    assert not {p.name for p in Path(folder).iterdir()} & set(PYTEST_CONFIG_FILES)
    assert not {p.name for p in tmp_path.rglob("*")} & set(PYTEST_CONFIG_FILES)
    assert [p.name for p in out.iterdir()] == ["tiff"]
    assert [p.name for p in tmp_path.iterdir()] == ["out"]
    for name, text in spec.files:
        raw = (Path(folder) / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.decode("utf-8") == text


def test_write_spec_refuses_existing_folder_without_overwrite(tmp_path):
    # Req 9.15
    spec = _emit("mystery_a")[2]
    assert not isinstance(write_spec(spec, tmp_path), EmitError)
    marker = tmp_path / "pbm" / "requirements.md"
    marker.write_text("sentinel", encoding="utf-8")
    assert isinstance(write_spec(spec, tmp_path), EmitError)
    assert marker.read_text(encoding="utf-8") == "sentinel"
    assert not isinstance(write_spec(spec, tmp_path, overwrite=True), EmitError)
    assert marker.read_text(encoding="utf-8") != "sentinel"


@pytest.mark.parametrize("slug", ["../x", "a/b", "A", "", ".."])
def test_write_spec_rejects_bad_slug(tmp_path, slug):
    # Req 9.15
    spec = _emit("mystery_a")[2]
    bad = EmittedSpec(slug=slug, files=spec.files)
    out = tmp_path / "out"
    out.mkdir()
    assert isinstance(write_spec(bad, out), EmitError)
    assert list(out.iterdir()) == []
    assert [p.name for p in tmp_path.iterdir()] == ["out"]


# --- Reference reader independence (design.md "Reference reader") -------------

def test_reference_reader_has_no_necropsy_import():
    src = (Path(__file__).parent / "support" / "reference_reader.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "necropsy" for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "necropsy"
    assert not re.search(r"^\s*(import|from)\s+necropsy", src, re.M)


# --- Property tests (task 11.9) -----------------------------------------------

from hypothesis import example, given, settings  # noqa: E402

from tests.support.inputs import engine_inputs  # noqa: E402
from tests.support.reference_reader import parse_candidates  # noqa: E402


def _with_corpus_examples(test):
    for name in reversed(CORPUS_NAMES):
        test = example(corpus_bytes(name))(test)
    return test


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_property_11_spec_emitter_is_total(data):
    """Feature: structure-inference-engine, Property 11: Spec emitter is total

    **Validates: Requirements 9.1, 9.6, 9.13, 6.4**
    """
    result = Engine().run(data)
    out = emit_spec(result, data)
    if result.status in ("RESOLVED", "UNRESOLVED_AMBIGUITY"):
        assert isinstance(out, EmittedSpec)
        assert tuple(n for n, _ in out.files) == expected_files(out.slug)
        assert len(out.files) == 3
        test_name = emitted_test_name(out.slug)
        assert fnmatch.fnmatch(test_name, "test_*.py")
        req = dict(out.files)["requirements.md"]
        assert len(BLOCK_RE.findall(req)) == 1
        layout = extract_layout(req)
        assert isinstance(layout, dict)
        assert layout["schema"] == "necropsy-layout/1"
        compile(dict(out.files)[test_name], test_name, "exec")
    else:
        assert result.status == "FAILED"
        assert isinstance(out, EmitError)


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_property_12_emitted_layout_reproduces_engine(data):
    """Feature: structure-inference-engine, Property 12: Emitted layout reproduces the engine

    **Validates: Requirements 9.16, 9.18**
    """
    result = Engine().run(data)
    if result.status == "RESOLVED":
        candidates = (result.candidate,)
    elif result.status == "UNRESOLVED_AMBIGUITY":
        candidates = result.candidates
    else:
        return
    spec = emit_spec(result, data)
    assert isinstance(spec, EmittedSpec)
    layout = extract_layout(dict(spec.files)["requirements.md"])
    assert isinstance(layout, dict)
    parsed = [p for p in parse_candidates(layout, data) if p.get("ok")]
    for cand in candidates:
        h = cand.hypothesis
        if h.encoding != "none":
            continue
        want = (h.width, h.height, h.bit_depth, cand.data_start, cand.data_end,
                bytes(cand.decoded))
        got = [(p["width"], p["height"], p["bit_depth"], p["data_start"],
                p["data_end"], p["pixels"]) for p in parsed]
        assert want in got, (want[:5], [g[:5] for g in got])


# --- Rule-breaking probe results are file layouts (Req 9.20) ----------------

def _craft_tiff_spp2():
    import struct
    n = 8 * 8  # 8 x 8, bits_per_sample 4 * samples_per_pixel 2 = 8 bits per pixel
    entries = [(256, 4, 8), (257, 4, 8), (258, 3, 4), (259, 3, 1), (273, 4, 8),
               (277, 3, 2), (279, 4, n)]
    data = b"II*\x00" + struct.pack("<I", 8 + n) + bytes((i * 7 + 3) % 256 for i in range(n))
    data += struct.pack("<H", len(entries))
    for tag, typ, val in entries:
        data += struct.pack("<HHII", tag, typ, 1, val)
    return data + struct.pack("<I", 0)


def test_rule_breaking_tiff_emits_file_layout_for_one_file_only():
    data = _craft_tiff_spp2()
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    assert any(r.source == "tiff" and r.reason == "probe_precondition_failed"
               for r in result.rejections)
    spec = emit_spec(result, data)
    assert isinstance(spec, EmittedSpec)
    req = _file(spec, "requirements.md")
    layout = extract_layout(req)
    assert layout["kind"] == "file" and layout["slug"] == "tiff"
    assert layout["image"] == {"width": 8, "height": 8, "bit_depth": 8, "row_alignment": 1}
    assert layout["data"]["start"] == 8 and layout["data"]["end"] == 72
    assert layout["data"]["encoding"] == "none"
    assert all(f["expect"] is None for f in layout["fields"])
    for doc in (req, _file(spec, "design.md")):
        assert "describes this one file only, not the format" in doc
    got = [p for p in parse_candidates(layout, data) if p.get("ok")]
    assert len(got) == 1
    p = got[0]
    assert (p["width"], p["height"], p["bit_depth"], p["data_start"], p["data_end"]) == (
        8, 8, 8, 8, 72)
    assert p["pixels"] == bytes(result.candidate.decoded) == data[8:72]


def test_mystery_e_still_emits_format_layout():
    assert _layout("mystery_e")["kind"] == "format"