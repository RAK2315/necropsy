"""Task 19.2: the optional photometric_interpretation entry (Requirement 9.26).

Written from the text of Requirement 9.26 only. "Unchanged" for mystery_e is checked by
absence: the entry and the EARS line are not in any emitted file, and the tag-table entry
names equal the eight the spec lists for tags 256, 257, 258, 259, 273, 277, 279, 284, plus predictor (Requirement 17.3). No
value is taken from the new code.
"""
from __future__ import annotations

import copy
from pathlib import Path

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.support.reference_reader import extract_layout, parse

ROOT = Path(__file__).resolve().parent.parent
GOIMAGE = ROOT / "spike" / "samples" / "real" / "goimage_bw-uncompressed.tiff"
MYSTERY_E = ROOT / "spike" / "samples" / "mystery_e"

EIGHT = ["width", "height", "bits_per_sample", "compression", "strip_offset",
         "samples_per_pixel", "strip_byte_count", "planar_configuration"]
# Requirement 17.3 (format-coverage Task 34): the emitted TIFF layout carries a ninth entry, predictor (tag 317),
# directly after planar_configuration; the optional entry still follows it.
WITH_PREDICTOR = EIGHT + ["predictor"]
ENTRY = {"name": "photometric_interpretation", "tag": 262, "default": None,
         "expect": None, "array": None, "optional": True}


def _emit(path):
    data = path.read_bytes()
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    return data, dict(emit_spec(result, data).files)


def _prose(requirements: str) -> list:
    """Lines of requirements.md outside the necropsy-layout block."""
    out, inside = [], False
    for line in requirements.splitlines():
        if line.startswith("```"):
            inside = not inside if "necropsy-layout" in line or inside else inside
            continue
        if not inside:
            out.append(line)
    return out


def test_goimage_layout_has_optional_entry_after_planar_configuration():
    _, files = _emit(GOIMAGE)
    layout = extract_layout(files["requirements.md"])
    entries = layout["tag_table"]["entries"]
    assert [e["name"] for e in entries] == WITH_PREDICTOR + ["photometric_interpretation"]
    assert entries[-1] == ENTRY
    assert list(entries[-1]) == list(ENTRY)  # key order as stated in 9.26
    assert layout["tag_table"]["entries"][:8] == [e for e in entries if e["name"] in EIGHT]


def test_goimage_requirements_has_one_ears_line():
    _, files = _emit(GOIMAGE)
    lines = [l for l in _prose(files["requirements.md"]) if "262" in l or "photometric" in l]
    assert len(lines) == 1
    line = lines[0]
    assert "WHERE" in line and "tag 262" in line and "`photometric_interpretation`" in line
    assert "SHALL read" in line and "adds no field" in line


def test_mystery_e_emission_has_no_optional_entry_or_line():
    data, files = _emit(MYSTERY_E)
    assert not any(f.name == "photometric_interpretation"
                   for f in Engine().run(data).candidate.hypothesis.fields)
    for text in files.values():
        assert "photometric" not in text and "262" not in text.replace("0x262", "")
    layout = extract_layout(files["requirements.md"])
    assert [e["name"] for e in layout["tag_table"]["entries"]] == WITH_PREDICTOR
    assert not any("optional" in e for e in layout["tag_table"]["entries"])


def test_reference_reader_round_trips_goimage_spec():
    data, files = _emit(GOIMAGE)
    layout = extract_layout(files["requirements.md"])
    out = parse(layout, data)
    assert out["ok"], out
    assert out["pixels"] == data[out["data_start"]:out["data_end"]]
    assert len(out["pixels"]) > 0
    assert "photometric_interpretation" in [f[0] for f in out["fields"]]


def test_reference_reader_absent_optional_tag_adds_no_field_and_does_not_raise():
    data, files = _emit(MYSTERY_E)
    base = extract_layout(files["requirements.md"])
    expected = parse(base, data)
    assert expected["ok"], expected
    crafted = copy.deepcopy(base)
    crafted["tag_table"]["entries"].append(dict(ENTRY))
    got = parse(crafted, data)
    assert got == expected
    assert "photometric_interpretation" not in [f[0] for f in got["fields"]]


def test_reference_reader_required_entry_still_errors_when_absent():
    data, files = _emit(MYSTERY_E)
    crafted = extract_layout(files["requirements.md"])
    crafted["tag_table"]["entries"].append(dict(ENTRY, optional=False, tag=262))
    assert parse(crafted, data)["ok"] is False
