"""Tests for necropsy.report.render (Requirements 8.4-8.7, Property 13).

Expected strings come from requirements.md 8.4-8.6 and design.md.
SPEC GAPS (wording left open, so only stated parts are asserted):
  * the stage line layout, the candidate line layout and the candidate
    numbering base/punctuation (8.5);
  * how a list is spelled in `revision_path: {revision_path}` (8.4);
  * the field-table column separators (8.4).
"""
import re

from hypothesis import given, settings

from necropsy.engine import Engine
from necropsy.report import render
from tests.conftest import corpus_bytes
from tests.support.inputs import engine_inputs


def _lines(name):
    return render(Engine().run(corpus_bytes(name))).split("\n")


def test_mystery_e_resolved_layout():
    lines = _lines("mystery_e")
    assert lines[0] == "RESOLVED"
    assert "closure: [86, 150) holds 64 bytes = 8 x 8" in lines
    # field table rows carry offsets as 0x%04X
    assert any(re.match(r"\s*0x[0-9A-F]{4}\b", ln) for ln in lines[1:])
    # 8.4: alternative_paths only when non-empty
    assert not any(ln.startswith("alternative_paths:") for ln in lines)


def test_mystery_b_rle_closure_and_trailer():
    lines = _lines("mystery_b")
    assert lines[0] == "RESOLVED"
    assert ("closure: rle_pcx decoded [128, 186) to 64 bytes = 8 x 8, "
            "all input consumed") in lines
    assert "trailer: pcx_palette_256" in lines


def test_mystery_h_revision_and_alternative_paths():
    lines = _lines("mystery_h")
    rev = [ln for ln in lines if ln.startswith("revision_path: ")]
    alt = [ln for ln in lines if ln.startswith("alternative_paths: ")]
    assert len(rev) == 1 and len(alt) == 1
    canonical = ("inclusive_bounds", "row_padding_variants")
    for line, names in ((rev[0], canonical), (alt[0], canonical[::-1])):
        assert line.index(names[0]) < line.index(names[1])


def test_mystery_d_ambiguity_rendering():
    result = Engine().run(corpus_bytes("mystery_d"))
    assert result.status == "UNRESOLVED_AMBIGUITY"
    assert len(result.candidates) == 18
    text = render(result)
    lines = text.split("\n")
    assert lines[0] == ("UNRESOLVED_AMBIGUITY: 18 candidates close; "
                        "the bytes cannot distinguish them")
    # every candidate is numbered (numbering base is a SPEC GAP: accept 0 or 1)
    for k in range(1, 19):
        assert re.search(r"(?<!\d)%d(?!\d)" % k, text), k
    # every candidate has exactly one coherence line, labelled heuristic
    coh = [ln for ln in lines if "coherence" in ln]
    assert len(coh) == 18
    for ln in coh:
        assert ("coherence (heuristic, row_mad_ratio): " in ln
                or "coherence (heuristic): " in ln)
    low = text.lower()
    for word in ("best", "preferred", "likely", "winner"):
        assert word not in low


def test_failure_report_input_too_short():
    result = Engine().run(b"\x00")
    assert result.status == "FAILED"
    assert render(result).split("\n")[0] == "FAILED: input_too_short"


def test_render_is_deterministic():
    for name in ("mystery_e", "mystery_d", "mystery_h"):
        result = Engine().run(corpus_bytes(name))
        assert render(result) == render(result)


# Feature: structure-inference-engine, Property 13: Pretty printer is total
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_property_13_pretty_printer_is_total(data):
    """**Validates: Requirements 8.4, 8.5, 8.6, 8.7**"""
    result = Engine().run(data)
    text = render(result)
    assert isinstance(text, str)
    assert text.split("\n")[0].startswith(result.status)
