"""Text renderer for EngineResult (Requirements 8.4 to 8.7). Pure; never raises."""

from __future__ import annotations

from necropsy.engine.types import (
    AmbiguousResult,
    Candidate,
    FailureReport,
    RejectionEntry,
    VerifiedHypothesis,
)


def _value(v: tuple) -> str:
    return repr(v[0]) if len(v) == 1 else repr(tuple(v))


def _field_table(c: Candidate) -> list[str]:
    rows = [
        ("0x%04X" % f.offset, f.name, f.fmt, _value(f.value))
        for f in c.hypothesis.fields
    ]
    head = ("offset", "field", "format", "value")
    widths = [max(len(r[i]) for r in [head] + rows) for i in range(4)]

    def line(r: tuple) -> str:
        return "  ".join(r[i].ljust(widths[i]) for i in range(4)).rstrip()

    return [line(head)] + [line(r) for r in rows]


def _closure_line(c: Candidate) -> str:
    h = c.hypothesis
    if h.encoding == "rle_pcx":
        return (
            f"closure: rle_pcx decoded [{c.data_start}, {c.data_end}) to "
            f"{c.expected_decoded_bytes} bytes = {c.row_stride} x {h.height}, "
            "all input consumed"
        )
    return (
        f"closure: [{c.data_start}, {c.data_end}) holds "
        f"{c.data_end - c.data_start} bytes = {c.row_stride} x {h.height}"
    )


def _resolved(r: VerifiedHypothesis) -> list[str]:
    c = r.candidate
    out = ["RESOLVED"]
    out += _field_table(c)
    out.append(_closure_line(c))
    if c.trailer:
        out.append(f"trailer: {c.trailer}")
    out.append(f"revision_path: {list(c.hypothesis.revision_path)}")
    if c.alternative_paths:
        out.append(f"alternative_paths: {[list(p) for p in c.alternative_paths]}")
    return out


def _coherence(c: Candidate) -> str:
    if c.coherence_status == "scored" and c.coherence_score is not None:
        return f"coherence (heuristic, {c.coherence_method}): {c.coherence_score:.4f}"
    return f"coherence (heuristic): {c.coherence_status}"


def _ambiguous(r: AmbiguousResult) -> list[str]:
    out = [
        f"UNRESOLVED_AMBIGUITY: {len(r.candidates)} candidates close; "
        "the bytes cannot distinguish them",
        f"stage: {r.stage}",
    ]
    for i, c in enumerate(r.candidates, 1):
        h = c.hypothesis
        out.append(
            f"candidate {i}: {h.width} x {h.height}, bit_depth={h.bit_depth}, "
            f"header_size={h.header_size}, alignment={h.row_alignment}, "
            f"encoding={h.encoding}"
        )
        out.append(f"  {_coherence(c)}")
    return out


def _rejection(i: int, e: RejectionEntry) -> str:
    s = f"{i}. {e.source}: {e.reason}"
    if e.discrepancy is not None:
        s += f" (discrepancy={e.discrepancy})"
    return s


def _failed(r: FailureReport) -> list[str]:
    out = [
        f"FAILED: {r.termination}",
        f"rejections: {len(r.rejections)}, checks: {r.total_checks}",
    ]
    out += [_rejection(i, e) for i, e in enumerate(r.rejections, 1)]
    return out


def render(result) -> str:
    try:
        if isinstance(result, VerifiedHypothesis):
            lines = _resolved(result)
        elif isinstance(result, AmbiguousResult):
            lines = _ambiguous(result)
        elif isinstance(result, FailureReport):
            lines = _failed(result)
        else:
            return "render error: TypeError"
        return "\n".join(lines)
    except Exception as exc:  # last line of defence: render never raises
        return f"render error: {type(exc).__name__}"
