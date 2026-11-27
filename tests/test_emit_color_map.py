"""Emitted text for `color_map` (render-fidelity Task 2.1; Requirements 7.6, 7.7, 8.2, 8.10 to 8.12).

tests/data/emit_pre_color_map_sha256.json holds, for each of the 11 samples and 81 corpus files, the
SHA-256 of every emitted file (criterion numbers stripped) taken from the commit before the emitter
described `color_map`.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.test_color_map import PALETTE_FILES, build_tiff
from tools import fc_diff

PINS = json.loads((Path(__file__).parent / "data" / "emit_pre_color_map_sha256.json").read_text(encoding="ascii"))
_BLOCK = re.compile(r"```necropsy-layout\n(.*?)\n```", re.S)
DESCRIPTION = re.compile(r"tag 320, SHORT \(3\), count (\d+), offset 0x([0-9A-F]{4}); "
                         r"3 \u00d7 2\^BitsPerSample values, not listed")


def _strip_numbers(text):
    return re.sub(r"(?m)^\d+\. ", "", text)


def _files(data):
    return dict(emit_spec(Engine().run(data), data).files)


def _without_color_map(name, text):
    """Remove the added description row, criterion line and layout entry; numbers stripped."""
    if name == "requirements.md":
        def block(m):
            lay = json.loads(m.group(1))
            lay["fields"] = [f for f in lay["fields"] if f["name"] != "color_map"]
            return "```necropsy-layout\n%s\n```" % json.dumps(lay, indent=2)
        text = _BLOCK.sub(block, text)
    lines = [ln for ln in text.split("\n")
             if "`color_map`" not in ln and not re.match(r"\| 0x[0-9A-F]{4} \| color_map \|", ln)
             and not ln.strip().startswith("# color_map:")]
    return _strip_numbers("\n".join(lines))


def test_pins_cover_every_sample_and_corpus_file():
    assert set(PINS) == {n for n, _ in fc_diff.sample_paths() + fc_diff.corpus_paths()}


def test_every_other_file_is_byte_identical_and_the_three_differ_only_by_color_map():
    changed = set()
    for name, path in fc_diff.sample_paths() + fc_diff.corpus_paths():
        want = PINS[name]
        data = path.read_bytes()
        spec = emit_spec(Engine().run(data), data)
        if "error" in want:
            assert not hasattr(spec, "files"), name
            continue
        files = dict(spec.files)
        got = {n: hashlib.sha256(_strip_numbers(t).encode("utf-8")).hexdigest() for n, t in files.items()}
        if got == want:
            continue
        changed.add(name)
        assert name in PALETTE_FILES, name
        for n, t in files.items():
            assert hashlib.sha256(_without_color_map(n, t).encode("utf-8")).hexdigest() == want[n], (name, n)
            assert "65535" not in t or n == "test_tiff.py"      # the test file embeds the source bytes only
    assert changed == PALETTE_FILES


@pytest.mark.parametrize("name,count,offset", [("libtiff_palette-1c-8b.tiff", 768, 0x5DCC),
                                               ("goimage_video-001-paletted.tiff", 768, 0x25CE),
                                               ("goimage_invalid-palette-ref.tiff", 195, 0x0025)])
def test_description_present_and_values_absent(name, count, offset):
    data = (fc_diff.REAL / name).read_bytes()
    r = Engine().run(data)
    cm = next(f for f in r.candidate.hypothesis.fields if f.name == "color_map")
    files = _files(data)
    desc = "tag 320, SHORT (3), count %d, offset 0x%04X; 3 \u00d7 2^BitsPerSample values, not listed" % (count, offset)
    assert desc in files["design.md"]
    assert "    # color_map: " + desc in files["test_tiff.py"]
    assert "`color_map` at offset 0x%04X" % offset in files["requirements.md"]
    for text in files.values():
        assert repr(cm.value) not in text and ", ".join(map(str, cm.value)) not in text
    assert "('color_map'" not in files["test_tiff.py"]


# Property 14 (Requirements 7.6, 7.7, 8.10, 8.11)
@settings(max_examples=25, deadline=None)
@given(st.lists(st.integers(0, 65535), min_size=768, max_size=768),
       st.lists(st.integers(0, 65535), min_size=768, max_size=768))
def test_emitted_text_describes_color_map_and_ignores_its_values(a, b):
    fa, fb = _files(build_tiff(values=tuple(a))), _files(build_tiff(values=tuple(b)))
    for name in ("design.md", "requirements.md"):
        assert fa[name] == fb[name]
    for files, vals in ((fa, a), (fb, b)):
        assert DESCRIPTION.search(files["design.md"]).group(1) == "768"
        assert repr(tuple(vals)) not in files["design.md"] + files["test_tiff.py"]
        assert "('color_map'" not in files["test_tiff.py"]
