"""public/samples/ is a byte-identical copy of the source samples, and the index says only what a fresh engine run finds.

UI clarity pass, task 24 (built by Claude Code, not Kiro): every sample carries one plain line, computed from a fresh
engine run, and the real-world sample ships with its MIT-CMU licence notice, linked from its row. This supersedes
necropsy-ui Requirement 11.4, which forbade any description of a sample; Rehaan approved the change on 25 Nov 2026.
"""
import hashlib
import json

import pytest

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from tools import copy_samples as cs

PUBLIC = REPO_ROOT / "public" / "samples"


def _index():
    return json.loads((PUBLIC / "index.json").read_text(encoding="utf-8"))


def test_nine_corpus_samples_then_the_external_ones_then_the_real_one():
    names = [e["name"] for e in _index()]
    assert names == ["mystery_" + c for c in "abcdefghi"] + ["external_a", "external_b", "pillow_odd_stride.pcx"]


@pytest.mark.parametrize("name", cs.NAMES)
def test_public_copy_is_byte_identical_to_source(name):
    assert (PUBLIC / name).read_bytes() == cs.source_of(name).read_bytes()


def test_real_sample_matches_the_corpus_manifest():
    got = hashlib.sha256((PUBLIC / cs.REAL_SAMPLE).read_bytes()).hexdigest()
    assert got == cs.manifest_sha256(cs.REAL_SAMPLE)


def test_index_matches_the_generator():
    assert _index() == cs.build_index()


def test_every_sample_has_one_plain_line_agreeing_with_a_fresh_engine_run():
    for e in _index():
        assert set(e) <= {"name", "size", "description", "provenance", "licence"}
        assert e["size"] == (PUBLIC / e["name"]).stat().st_size
        r = Engine(deadline_seconds=5.0).run((PUBLIC / e["name"]).read_bytes())
        d = e["description"]
        if r.status == "RESOLVED":
            h = r.candidate.hypothesis
            assert d.startswith(f"One reading fits: {h.width} × {h.height}, {h.bit_depth}-bit"), (e["name"], d)
            assert ("as the header declares" in d) == (not h.revision_path), (e["name"], d)
        elif r.status == "UNRESOLVED_AMBIGUITY":
            assert d == f"{len(r.candidates)} readings fit exactly. NECROPSY does not choose.", (e["name"], d)
        else:
            assert d.startswith("Not recovered"), (e["name"], d)


def test_descriptions_translate_and_never_diagnose():
    # the engine finds that a layout fits; it never finds that a file is broken, lying, truncated or corrupt
    for e in _index():
        low = e["description"].lower()
        for word in ("lie", "lying", "wrong", "false", "corrupt", "broken", "truncated", "cut short", "damaged", "real "):
            assert word not in low, (e["name"], word)


def test_provenance_and_licence():
    for e in _index():
        if e["name"].startswith("external_"):
            assert e["provenance"].startswith("written by Pillow ") and "licence" not in e
        elif e["name"] == cs.REAL_SAMPLE:
            assert e["provenance"] == "from Pillow's test suite (MIT-CMU)"
            assert e["licence"] == "LICENSES/Pillow-MIT-CMU.txt"
            notice = (PUBLIC / e["licence"]).read_text(encoding="utf-8")
            assert notice == (cs.REAL / "LICENSES" / "Pillow-MIT-CMU.txt").read_text(encoding="utf-8")
            assert "Secret Labs AB" in notice and "Permission to use, copy, modify" in notice
        else:
            assert "provenance" not in e and "licence" not in e
