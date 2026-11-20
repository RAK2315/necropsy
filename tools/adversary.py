"""Blind wrong-layout generator and measurement for the closure gate (gate-adversary spec).

This is a MEASUREMENT, not a pass/fail test. The generator draws from a space
the engine cannot reach (it invents header sizes; the engine takes them from a
declared field or from generic search's defined axes), so a layout that closes
here is not a reachable defect. The result shows how much of the gate's
strength comes from closure alone: see design.md, "Finding".

The generator takes the file size and nothing else. It never sees the file's
bytes or the engine's result, so what it produces cannot depend on what the
engine found. `run_adversary` is the only place that reads the engine's
candidates, and only to decide which generated layouts are excluded.

Run: python -m tools.adversary   (writes tools/adversary_counts.json)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from necropsy.engine.closure import check_closure, row_stride
from necropsy.engine.types import Hypothesis, hypothesis_key

# Axis values. Stated in the spec (design.md, "Axes"); change both together.
GRID_MAX = 24                                   # width and height 1..GRID_MAX
BIT_DEPTHS = (1, 2, 4, 8, 16, 24, 32)
ALIGNMENTS = (1, 2, 4)
ENCODINGS = ("none", "rle_pcx")
ORIGINS = ("generic", "pcx", "tga", "pbm")      # trailer-registry origins, plus one that matches none
HEADER_CONSTANTS = (0, 7, 8, 12, 18, 26, 40, 54, 86, 96, 128)
FILL_DELTAS = (-1, 0, 1)
TRAILER_LENGTHS = (0, 26, 769)                  # sizes of the two trailer shapes in the registry
STRIP_DELTAS = (-2, -1, 0, 1, 2)
STRIP_SHORT_SIDES = (1, 2, 3)
SWEEP_GRID_MAX = 6                              # header sweep: every header 0..HEADER_SWEEP_MAX
HEADER_SWEEP_MAX = 160
ORIGIN_GRID_MAX = 8                             # origin sweep: every origin, constant headers
END_BACKOFFS = (1, 2, 3, 4, 8, 26, 769)         # declared data_end = size - backoff
END_GRID_MAX = 8


def _hyp(w, h, bd, hdr, al, enc, origin, end=None) -> Hypothesis:
    return Hypothesis(w, h, bd, hdr, al, enc, end, (), origin)


def _consts(size: int) -> list[int]:
    return [c for c in HEADER_CONSTANTS if c <= size + 1]


def generate_layouts(size: int) -> Iterator[Hypothesis]:
    """Yield wrong-by-construction layout guesses for a file of `size` bytes.

    Input is an int on purpose: the generator cannot read the file or the engine.
    Order and content depend only on `size`. No layout is yielded twice.
    """
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        return
    consts = _consts(size)

    # Axis 1: width x height grid x depth x row alignment x encoding x header.
    # Headers are the constants plus "exact fill" headers computed from size
    # alone: the header that would make a raw layout consume the whole file,
    # or the file minus a trailer, give or take one. Origin "generic".
    for w in range(1, GRID_MAX + 1):
        for h in range(1, GRID_MAX + 1):
            for bd in BIT_DEPTHS:
                for al in ALIGNMENTS:
                    total = row_stride(w, bd, al) * h
                    hs = set(consts)
                    for t in TRAILER_LENGTHS:
                        for d in FILL_DELTAS:
                            f = size - total - t + d
                            if 0 <= f <= size + 1:
                                hs.add(f)
                    for enc in ENCODINGS:
                        for hdr in sorted(hs):
                            yield _hyp(w, h, bd, hdr, al, enc, "generic")

    # Axis 2: header sweep. Every header size 0..HEADER_SWEEP_MAX on a small
    # grid, skipping the headers axis 1 already covered for that combination.
    for w in range(1, SWEEP_GRID_MAX + 1):
        for h in range(1, SWEEP_GRID_MAX + 1):
            for bd in BIT_DEPTHS:
                for al in ALIGNMENTS:
                    total = row_stride(w, bd, al) * h
                    done = set(consts)
                    for t in TRAILER_LENGTHS:
                        for d in FILL_DELTAS:
                            done.add(size - total - t + d)
                    for enc in ENCODINGS:
                        for hdr in range(0, min(size + 1, HEADER_SWEEP_MAX) + 1):
                            if hdr not in done:
                                yield _hyp(w, h, bd, hdr, al, enc, "generic")

    # Axis 3: trailer-registry origin. The other three origins on a small grid,
    # constant headers ("generic" was covered above).
    for w in range(1, ORIGIN_GRID_MAX + 1):
        for h in range(1, ORIGIN_GRID_MAX + 1):
            for bd in BIT_DEPTHS:
                for al in ALIGNMENTS:
                    for enc in ENCODINGS:
                        for hdr in consts:
                            for origin in ORIGINS[1:]:
                                yield _hyp(w, h, bd, hdr, al, enc, origin)

    # Axis 4: long thin strips. One side is a small count, the other is the
    # count that would fill (size - header) at this depth, plus small deltas.
    # Strips with the long side inside the grid were yielded by axis 1.
    seen: set[tuple] = set()
    for hdr in consts:
        for bd in BIT_DEPTHS:
            base = ((size - hdr) * 8) // bd
            for d in STRIP_DELTAS:
                long_side = base + d
                if long_side <= GRID_MAX:
                    continue
                for short in STRIP_SHORT_SIDES:
                    for (w, h) in ((long_side, short), (short, long_side)):
                        for al in ALIGNMENTS:
                            for enc in ENCODINGS:
                                k = (w, h, bd, hdr, al, enc)
                                if k not in seen:
                                    seen.add(k)
                                    yield _hyp(w, h, bd, hdr, al, enc, "generic")

    # Axis 5: declared data end short of the file end. Never equal to size,
    # which would only re-spell "no declared end".
    for w in range(1, END_GRID_MAX + 1):
        for h in range(1, END_GRID_MAX + 1):
            for bd in BIT_DEPTHS:
                for al in ALIGNMENTS:
                    for enc in ENCODINGS:
                        for hdr in consts:
                            for back in END_BACKOFFS:
                                if size - back >= 0:
                                    yield _hyp(w, h, bd, hdr, al, enc, "generic", size - back)


@dataclass(frozen=True)
class AdversaryCounts:
    generated: int            # layouts the generator produced
    excluded: int             # of those, layouts whose key is one the engine reported
    tried: int                # wrong layouts run through the gate (generated - excluded)
    closed: int               # tried layouts that closed and are not a re-spelling of a candidate
    respelled: int            # tried layouts that closed as the same physical layout as a candidate
    closed_examples: tuple    # up to 10 closing layouts, for the failure message


def _physical(h: Hypothesis, v) -> tuple:
    return (h.width, h.height, h.bit_depth, h.header_size,
            row_stride(h.width, h.bit_depth, h.row_alignment), h.encoding,
            v.data_start, v.data_end)


def candidate_set(result) -> list:
    """The engine's reported candidates for any EngineResult."""
    if result.status == "RESOLVED":
        return [result.candidate]
    return list(getattr(result, "candidates", ()))


def run_adversary(data: bytes, result, gate: Callable = check_closure) -> AdversaryCounts:
    """Run every blind layout for len(data) through `gate`.

    `result` is the engine's result for `data`. It is used only to exclude the
    engine's reported candidates from the count; it does not influence generation.
    """
    cands = candidate_set(result)
    keys = {hypothesis_key(c.hypothesis) for c in cands}
    physical = {(c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth,
                 c.hypothesis.header_size, c.row_stride, c.hypothesis.encoding,
                 c.data_start, c.data_end) for c in cands}
    generated = excluded = closed = respelled = 0
    examples: list = []
    for h in generate_layouts(len(data)):
        generated += 1
        if hypothesis_key(h) in keys:
            excluded += 1
            continue
        v = gate(h, data)
        if not v.ok:
            continue
        if _physical(h, v) in physical:
            respelled += 1
            continue
        closed += 1
        if len(examples) < 10:
            examples.append(h)
    return AdversaryCounts(generated, excluded, generated - excluded, closed, respelled, tuple(examples))


ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "spike" / "samples"
OUT = Path(__file__).resolve().parent / "adversary_counts.json"


def sample_paths() -> list[Path]:
    """Every sample file: the corpus in spike/samples/ and the two external samples."""
    files = sorted(p for p in SAMPLES.iterdir() if p.is_file())
    files += sorted(p for p in (SAMPLES / "external").iterdir() if p.name.startswith("external_"))
    return files


def measure_all() -> dict:
    from necropsy.engine import Engine
    rows = {}
    for p in sample_paths():
        data = p.read_bytes()
        result = Engine().run(data)
        c = run_adversary(data, result)
        rows[p.name] = {
            "size": len(data),
            "status": result.status,
            "reported_candidates": len(candidate_set(result)),
            "generated": c.generated,
            "excluded_reported": c.excluded,
            "tried": c.tried,
            "closed": c.closed,
            "closed_rate": round(c.closed / c.tried, 4) if c.tried else 0.0,
            "respelled_candidate": c.respelled,
            "closed_examples": [
                {"width": h.width, "height": h.height, "bit_depth": h.bit_depth,
                 "header_size": h.header_size, "row_alignment": h.row_alignment,
                 "encoding": h.encoding, "data_end": h.data_end}
                for h in c.closed_examples[:3]],
        }
    tried = sum(r["tried"] for r in rows.values())
    closed = sum(r["closed"] for r in rows.values())
    return {"samples": rows, "total_tried": tried, "total_closed": closed,
            "total_closed_rate": round(closed / tried, 4) if tried else 0.0}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    report = measure_all()
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, r in report["samples"].items():
        print(f"{name:12} tried {r['tried']:>8} closed {r['closed']:>6} "
              f"({r['closed_rate']:.2%}) respelled {r['respelled_candidate']}")
    print(f"total        tried {report['total_tried']:>8} closed {report['total_closed']:>6} "
          f"({report['total_closed_rate']:.2%})")
