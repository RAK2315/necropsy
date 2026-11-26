"""Requirement 17.11: the emitted spec of every file whose layout did not change differs from the
emitter's output before this spec (Task 29 onwards) only in what Requirements 17.2 and 17.3 change.

tests/data/emit_pre_t29_sha256.json holds, for each of the 11 samples and 81 corpus files, the
SHA-256 of every emitted file (criterion numbers stripped, because inserted definition lines
renumber the criteria), taken from commit fa3b6ae, the last commit before the emitter changed.
"""
import hashlib
import json
import re
from pathlib import Path

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tools import fc_diff

PINS = json.loads((Path(__file__).parent / "data" / "emit_pre_t29_sha256.json").read_text(encoding="ascii"))
_BLOCK = re.compile(r"```necropsy-layout\n(.*?)\n```", re.S)
_DEFINED = ("rle_tga", "packbits", "lzw_tiff", "deflate_zlib", "lzma_xz")
# Task 36 follow-up (Requirement 17.1, 17.11): the closure line of the four compressed TIFF
# encodings names them and defers to their end rules; undone here to the line the pins hold.
_NEW_CLOSURE = re.compile(r"WHEN the encoding is (packbits|lzw_tiff|deflate_zlib|lzma_xz), THE parser SHALL "
                          r"require the decoder to end as its definition above states and to produce "
                          r"exactly the expected bytes for each data range\.$")
_RUN_LENGTH = ("WHEN the encoding is a run-length encoding, THE parser SHALL require the decoder to "
               "consume the whole data region and produce exactly row_stride \u00d7 height bytes.")


def _strip_numbers(text):
    return re.sub(r"(?m)^\d+\. ", "", text)


def _undo(name, text):
    """Reverse the differences Requirements 17.2 and 17.3 allow (and the 17.1 definitions they
    bring), then strip criterion numbers."""
    if name != "requirements.md":
        return _strip_numbers(text)

    def block(m):
        lay = json.loads(m.group(1))
        enc = lay.get("data", {}).get("encoding") if isinstance(lay.get("data"), dict) else None
        values = enc.get("values") if isinstance(enc, dict) else None
        if not isinstance(values, dict):
            return m.group(0)
        if lay.get("tag_table"):  # TIFF: 17.3
            lay["data"]["encoding"]["values"] = {"1": "none"}
            lay["tag_table"]["entries"] = [
                e for e in lay["tag_table"]["entries"] if e["name"] != "predictor"]
        else:  # TGA: 17.2
            for k in ("9", "10", "11"):
                if values.get(k) == "rle_tga":
                    values[k] = "unsupported"
        return "```necropsy-layout\n%s\n```" % json.dumps(lay, indent=2)

    text = _BLOCK.sub(block, text)
    text = re.sub(r"(?<=, )(9|10|11) \u2192 `rle_tga`", "\\1 \u2192 `unsupported`", text)
    text = re.sub(r"\(1 \u2192 `none`, [^)]*`packbits`[^)]*\), otherwise `unsupported`",
                  "(1 \u2192 `none`), otherwise `unsupported`", text)
    keep = [_RUN_LENGTH if _NEW_CLOSURE.match(ln) else ln for ln in _strip_numbers(text).split("\n")
            if not re.match(r"WHEN the encoding is `(%s)`" % "|".join(_DEFINED), ln)
            and "tag entry `predictor`" not in ln]
    return "\n".join(keep)


def _layout_changed(result):
    """True when a candidate's layout is one this spec adds (Requirements 17.4, 17.5, 17.6)."""
    cands = list(getattr(result, "candidates", ()) or ())
    if getattr(result, "candidate", None) is not None:
        cands.append(result.candidate)
    return any(c.hypothesis.ranges or c.hypothesis.planes > 1 or c.hypothesis.probe_name == "pnm"
               for c in cands)


def test_pins_cover_every_sample_and_corpus_file():
    names = {n for n, _ in fc_diff.sample_paths() + fc_diff.corpus_paths()}
    assert set(PINS) == names and len(names) == 92


def test_unchanged_layouts_differ_only_by_requirements_17_2_and_17_3():
    compared = 0
    for name, path in fc_diff.sample_paths() + fc_diff.corpus_paths():
        want = PINS[name]
        data = path.read_bytes()
        result = Engine().run(data)
        spec = emit_spec(result, data)
        if "error" in want:
            continue  # refused before; its new layout is covered by the per-layout emission tests
        assert hasattr(spec, "files"), (name, getattr(spec, "message", spec))
        if _layout_changed(result):
            continue
        got = {n: hashlib.sha256(_undo(n, t).encode("utf-8")).hexdigest() for n, t in sorted(spec.files)}
        assert got == want, name
        compared += 1
    assert compared >= 40, compared
