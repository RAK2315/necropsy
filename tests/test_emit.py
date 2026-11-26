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

def _craft_tiff_planar2():
    import struct
    n = 8 * 8  # 8 x 8, 8 bits per pixel; planar_configuration 2 breaks the TIFF rule (tag 284 must be 1)
    entries = [(256, 4, 8), (257, 4, 8), (258, 3, 8), (259, 3, 1), (273, 4, 8),
               (277, 3, 1), (279, 4, n), (284, 3, 2)]
    data = b"II*\x00" + struct.pack("<I", 8 + n) + bytes((i * 7 + 3) % 256 for i in range(n))
    data += struct.pack("<H", len(entries))
    for tag, typ, val in entries:
        data += struct.pack("<HHII", tag, typ, 1, val)
    return data + struct.pack("<I", 0)


def test_rule_breaking_tiff_emits_file_layout_for_one_file_only():
    data = _craft_tiff_planar2()
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

# --- TGA 2.0 footer in emitted layouts (Req 9.16, 1.5) -----------------------
TGA2_SIGNATURE_HEX = "54525545564953494f4e2d5846494c452e00"  # "TRUEVISION-XFILE.\0"


def _external_b():
    from tests.conftest import SAMPLES_DIR
    return (SAMPLES_DIR / "external" / "external_b").read_bytes()


def test_tga_layout_lists_tga2_footer_with_signature():
    layout = _layout("mystery_c")
    trailers = layout["data"]["trailers"]
    footer = [t for t in trailers if t["name"] == "tga2_footer"]
    assert len(footer) == 1
    assert footer[0]["length"] == 26
    assert footer[0]["signature"] == TGA2_SIGNATURE_HEX
    assert footer[0]["signature_offset"] == 8


TGA2_DECLARED = [{"name": "extension_area_offset", "at": 0, "fmt": "<I"},
                 {"name": "developer_area_offset", "at": 4, "fmt": "<I"}]
TGA2_AREA = {"base": "extension_area_offset", "size_at": 0, "size_fmt": "<H", "min_size": 495,
             "offsets": [{"name": "colour_correction_offset", "at": 482, "fmt": "<I"},
                         {"name": "postage_stamp_offset", "at": 486, "fmt": "<I"},
                         {"name": "scan_line_offset", "at": 490, "fmt": "<I"}]}


def test_tga_layout_carries_declared_offsets_and_area():
    # Req 9.23; design.md "Layout schema"
    layout = _layout("mystery_c")
    footer = [t for t in layout["data"]["trailers"] if t["name"] == "tga2_footer"][0]
    assert footer["declared_offsets"] == TGA2_DECLARED
    assert footer["area"] == TGA2_AREA
    assert json.loads(json.dumps(layout)) == layout


def test_pcx_layout_trailer_is_unchanged():
    # Req 9.23: pcx_palette_256 declares nothing, so neither key appears
    layout = _layout("mystery_b")
    assert layout["data"]["trailers"] == [
        {"name": "pcx_palette_256", "length": 769, "signature": "0c", "signature_offset": 0}]


def test_reference_reader_imports_only_json_re_struct():
    # design.md "Reference reader"
    src = (Path(__file__).parent / "support" / "reference_reader.py").read_text(encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods == {"json", "re", "struct", "zlib", "lzma"}  # Req 17.8: zlib and lzma are allowed (Task 33)


def test_reference_reader_reproduces_external_b_from_emitted_requirements():
    data = _external_b()
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    spec = emit_spec(result, data)
    assert isinstance(spec, EmittedSpec)
    layout = extract_layout(_file(spec, "requirements.md"))
    trailers = layout["data"]["trailers"]
    assert any(t["name"] == "tga2_footer" and t["signature"] == TGA2_SIGNATURE_HEX
               and t["signature_offset"] == 8 for t in trailers)
    got = [p for p in parse_candidates(layout, data) if p.get("ok")]
    assert len(got) == 1
    p = got[0]
    assert (p["width"], p["height"], p["bit_depth"]) == (64, 48, 24)
    assert (p["data_start"], p["data_end"]) == (18, 9234)
    assert p["pixels"] == bytes(result.candidate.decoded)


# --- TIFF BitsPerSample array and planar_configuration (Req 9.21, 9.22, 7.13) ---

REAL_TIFFS = {
    "goimage_no_compress.tiff": (16, 15, 32, 8, 968),
    "goimage_no_rps.tiff": (16, 15, 32, 8, 968),
    "goimage_video-001-uncompressed.tiff": (150, 103, 24, 8, 46358),
    "sdlimage_sample.tif": (23, 42, 24, 8, 2906),
}


def _real_tiff(name):
    from tests.conftest import SAMPLES_DIR
    return (SAMPLES_DIR / "real" / name).read_bytes()


@pytest.mark.parametrize("name", sorted(REAL_TIFFS))
def test_real_tiff_array_layout_reproduced_and_emitted_suite_passes(name, tmp_path):
    import subprocess
    import sys
    from tests.support.reference_reader import make_parser_module, parse
    width, height, depth, start, end = REAL_TIFFS[name]
    data = _real_tiff(name)
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    spec = emit_spec(result, data)
    assert isinstance(spec, EmittedSpec)
    req = _file(spec, "requirements.md")
    layout = extract_layout(req)
    assert layout["kind"] == "format"
    assert "all equal" in req and "planar_configuration" in req
    assert re.search(r"planar_configuration.{0,60}is not 1", req)
    p = parse(layout, data)
    assert p["ok"], p
    assert (p["width"], p["height"], p["bit_depth"], p["data_start"], p["data_end"]) == (
        width, height, depth, start, end)
    assert p["pixels"] == bytes(result.candidate.decoded) == data[start:end]
    for fname, text in spec.files:
        (tmp_path / fname).write_text(text, encoding="utf-8")
    (tmp_path / "parser_tiff.py").write_text(make_parser_module(req), encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path), "-q"],
                          cwd=str(tmp_path), capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _tiff_with(entries, extra=b""):
    import struct
    body = b"II*\x00" + struct.pack("<I", 8 + len(extra))
    body += extra + struct.pack("<H", len(entries))
    for tag, typ, cnt, val in entries:
        body += struct.pack("<HHII", tag, typ, cnt, val)
    return body + struct.pack("<I", 0)


def test_reference_reader_array_and_expect_rules():
    from tests.support.reference_reader import parse
    layout = _layout("mystery_e")
    data = _real_tiff("sdlimage_sample.tif")
    assert parse(layout, data)["ok"]
    # 3 SHORT values at a pointer: equal -> ok, unequal -> error.
    def build(vals, planar):
        pix = bytes(8 * 8 * 3)
        extra = pix + b"".join(v.to_bytes(2, "little") for v in vals)
        ptr = 8 + len(pix)
        return _tiff_with([(256, 4, 1, 8), (257, 4, 1, 8), (258, 3, 3, ptr), (259, 3, 1, 1),
                           (273, 4, 1, 8), (277, 3, 1, 3), (279, 4, 1, len(pix)),
                           (284, 3, 1, planar)], extra)
    ok = parse(layout, build([8, 8, 8], 1))
    assert ok["ok"] and ok["bit_depth"] == 24
    assert [f for f in ok["fields"] if f[0] == "bits_per_sample"].__len__() == 3
    assert not parse(layout, build([8, 8, 4], 1))["ok"]
    assert not parse(layout, build([8, 8, 8], 2))["ok"]