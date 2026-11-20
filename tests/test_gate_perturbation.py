"""Perturbation test (gate-adversary spec): change one declared dimension byte, re-run the engine.

Claim under test: a probe reads the file rather than recognising it. After a
declared width or height is changed, the engine either fails or returns layouts
whose changed dimension follows the new declared value. It must never return
the unperturbed answer.

Byte offsets and formats (declared in design.md, "Perturbation"):
  PCX   xmax  0x08 <H, ymax 0x0A <H. Width is xmax+1 by the inclusive convention.
  TGA   width 0x0C <H, height 0x0E <H.
  TIFF  ImageWidth (tag 256) and ImageLength (tag 257) entries, value field at entry+8, ">H" for MM.
  PBM   P4 header "P4\\n<w> <h>\\n": width digit at 3, height digit at 5, one ASCII digit each.
"""
import struct
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.types import hypothesis_key
from tests.conftest import SAMPLES_DIR, corpus_bytes

# name -> (format, {axis: (offset, struct fmt or "ascii1", original declared value)})
SAMPLES = {
    "mystery_a": ("pbm", {"width": (3, "ascii1", 4), "height": (5, "ascii1", 4)}),
    "mystery_b": ("pcx", {"width": (0x08, "<H", 7), "height": (0x0A, "<H", 7)}),
    "mystery_i": ("pcx", {"width": (0x08, "<H", 7), "height": (0x0A, "<H", 7)}),
    "mystery_h": ("pcx", {"width": (0x08, "<H", 5), "height": (0x0A, "<H", 5)}),
    "external_a": ("pcx", {"width": (0x08, "<H", 63), "height": (0x0A, "<H", 47)}),
    "mystery_c": ("tga", {"width": (0x0C, "<H", 16), "height": (0x0E, "<H", 16)}),
    "external_b": ("tga", {"width": (0x0C, "<H", 64), "height": (0x0E, "<H", 48)}),
    "mystery_e": ("tiff", {"width": (None, ">H", 8), "height": (None, ">H", 8)}),
}
TIFF_TAGS = {"width": 256, "height": 257}


def load(name: str) -> bytes:
    if name.startswith("external_"):
        return (SAMPLES_DIR / "external" / name).read_bytes()
    return corpus_bytes(name)


def tiff_value_offset(data: bytes, tag: int) -> int:
    """Independent IFD walk for a big-endian TIFF: offset of the value field of `tag`'s entry."""
    ifd = struct.unpack_from(">I", data, 4)[0]
    count = struct.unpack_from(">H", data, ifd)[0]
    for k in range(count):
        entry = ifd + 2 + 12 * k
        if struct.unpack_from(">H", data, entry)[0] == tag:
            return entry + 8
    raise AssertionError(f"tag {tag} not found")


def locate(name: str, axis: str) -> tuple[int, str, int]:
    fmt, axes = SAMPLES[name]
    offset, code, original = axes[axis]
    if fmt == "tiff":
        offset = tiff_value_offset(load(name), TIFF_TAGS[axis])
    return offset, code, original


def read_declared(data: bytes, offset: int, code: str) -> int:
    if code == "ascii1":
        return int(chr(data[offset]))
    return struct.unpack_from(code, data, offset)[0]


def perturb(name: str, axis: str, new: int) -> bytes | None:
    """The sample with one declared dimension replaced; None if `new` does not fit the field."""
    data = bytearray(load(name))
    offset, code, _ = locate(name, axis)
    if code == "ascii1":
        if not 0 <= new <= 9:
            return None
        data[offset] = ord(str(new))
    else:
        if not 0 <= new <= 0xFFFF:
            return None
        struct.pack_into(code, data, offset, new)
    return bytes(data)


def candidates(result) -> list:
    if result.status == "RESOLVED":
        return [result.candidate]
    return list(getattr(result, "candidates", ()))


def classify(name: str, axis: str, new: int) -> str:
    """Assert the claim for one perturbation. Returns "failed" or "tracked"."""
    fmt = SAMPLES[name][0]
    original_keys = {hypothesis_key(c.hypothesis) for c in candidates(Engine().run(load(name)))}
    assert original_keys, "the unperturbed sample must produce candidates"
    data = perturb(name, axis, new)
    assert data is not None
    result = Engine().run(data)
    if result.status == "FAILED":
        return "failed"
    allowed = {new, new + 1} if fmt == "pcx" else {new}   # PCX bounds are inclusive
    for c in candidates(result):
        key = hypothesis_key(c.hypothesis)
        assert key not in original_keys, (
            f"{name} {axis}={new}: engine returned the unperturbed answer {key}")
        dim = c.hypothesis.width if axis == "width" else c.hypothesis.height
        assert dim in allowed, (
            f"{name} {axis}={new}: candidate {axis} {dim} follows neither the declared value nor its "
            f"inclusive form {sorted(allowed)}")
    return "tracked"


def deltas(original: int) -> list[int]:
    return sorted({original - 2, original - 1, original + 1, original + 2, 2 * original, 0, 1} - {original})


CASES = [(n, a, v) for n, (fmt, axes) in SAMPLES.items() for a in axes for v in deltas(axes[a][2])]


@pytest.mark.parametrize("name,axis,new", CASES, ids=[f"{n}-{a}-{v}" for n, a, v in CASES])
def test_perturbed_dimension_is_tracked_or_fails(name, axis, new):
    if perturb(name, axis, new) is None:
        pytest.skip("value does not fit the field")
    classify(name, axis, new)


@pytest.mark.parametrize("name", list(SAMPLES))
def test_table_offsets_hold_the_declared_values(name):
    # Grounds the table: the bytes at each offset really are the dimension the table says.
    data = load(name)
    for axis in SAMPLES[name][1]:
        offset, code, original = locate(name, axis)
        assert read_declared(data, offset, code) == original


@pytest.mark.parametrize("name", list(SAMPLES))
def test_some_perturbation_of_each_sample_is_tracked(name):
    # Not vacuous: for every sample at least one perturbation yields a changed, followed answer.
    outcomes = []
    for axis in SAMPLES[name][1]:
        for v in deltas(SAMPLES[name][1][axis][2]):
            if perturb(name, axis, v) is not None:
                outcomes.append(classify(name, axis, v))
    assert "tracked" in outcomes


@settings(max_examples=150, deadline=None)
@given(st.sampled_from(sorted(SAMPLES)), st.sampled_from(["width", "height"]),
       st.integers(min_value=0, max_value=0xFFFF))
def test_property_any_declared_dimension_is_tracked_or_fails(name, axis, new):
    if perturb(name, axis, new) is None or new == locate(name, axis)[2]:
        return
    classify(name, axis, new)


def test_a_recogniser_would_be_caught(monkeypatch):
    # Teeth: an engine that recognises the file and ignores the perturbed byte returns the old answer.
    original = {name: Engine().run(load(name)) for name in ("external_a",)}

    class Recogniser:
        def run(self, data):
            return original["external_a"]

    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "Engine", Recogniser)
    with pytest.raises(AssertionError, match="unperturbed answer"):
        classify("external_a", "width", 62)
