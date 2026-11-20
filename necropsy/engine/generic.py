"""Generic Search: infer width, height and bit depth from arbitrary bytes.

Width plus bit depth fixes the height, so reads are grouped by value and the
height is looked up instead of being searched. Every closer is collected; the
search never returns early on success.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .budget import Budget
from .closure import check_closure, rle_pcx_output_length, row_stride
from .trailers import match_trailer, trailer_data_end_detail
from .types import FieldRecord, Hypothesis, hypothesis_key

HEADER_LENGTHS = tuple(range(4, 257, 4))
WIDTH_HEIGHT_FORMATS = ("<H", ">H", "<I", ">I", "<i", ">i")
FORMAT_SIZE = {"<H": 2, ">H": 2, "<I": 4, ">I": 4, "<i": 4, ">i": 4}
VALID_BIT_DEPTHS = (1, 4, 8, 16, 24, 32)


@dataclass(frozen=True)
class GenericOutcome:
    found: tuple  # ((Hypothesis, ClosureVerdict), ...) in discovery order
    stop: str | None  # None, "deadline_exceeded" or "search_cap_exceeded"


def _fields(w_reads, h_reads, b_offsets, data, bit_depth) -> tuple[FieldRecord, ...]:
    out = [FieldRecord("width", o, f, struct.unpack_from(f, data, o)) for f, o in w_reads]
    out += [FieldRecord("height", o, f, struct.unpack_from(f, data, o)) for f, o in h_reads]
    out += [FieldRecord("bit_depth", o, "B", (bit_depth,)) for o in b_offsets]
    return tuple(out)


def generic_search(data: bytes, budget: Budget, on_reject) -> GenericOutcome:
    """Never raises. A last-resort handler returns the candidates found so far
    with stop=None: an internal error ends the search quietly, and anything
    already verified is still valid because each was closure-checked."""
    found: dict = {}
    try:
        return _search(data, budget, on_reject, found)
    except Exception:
        return GenericOutcome(tuple(found.values()), None)


def _search(data, budget, on_reject, found) -> GenericOutcome:
    for L in HEADER_LENGTHS:
        if L >= len(data):
            break
        stop = budget.stop_reason()
        if stop:
            return GenericOutcome(tuple(found.values()), stop)
        reads: dict = {}
        for f in WIDTH_HEIGHT_FORMATS:
            for o in range(0, L - FORMAT_SIZE[f] + 1):
                v = struct.unpack_from(f, data, o)[0]
                if v > 0:
                    reads.setdefault(v, []).append((f, o))
        depths: dict = {}
        for o in range(L):
            if data[o] in VALID_BIT_DEPTHS:
                depths.setdefault(data[o], []).append(o)
        end, trailer, t_err, t_detail = trailer_data_end_detail(data, L, "generic")
        matched = match_trailer(data, L, "generic")[1] is not None
        if t_err:
            on_reject(None, None, reason=t_err, detail=t_detail)
            sizes = []
        else:
            sizes = [("none", end - L, None)]
            if trailer == "pcx_palette_256":
                n = rle_pcx_output_length(data, L, end)
                if n:
                    sizes.append(("rle_pcx", n, None))
        if matched:  # end-of-file reading follows the trailer reading (Requirement 1.17)
            sizes.append(("none", len(data) - L, len(data)))
        for enc, S, declared_end in sizes:
            if S <= 0:
                continue
            for W, w_reads in reads.items():
                for B in depths:
                    stride = row_stride(W, B, 1)
                    if stride <= 0 or S % stride:
                        continue
                    Hh = S // stride
                    h_reads = reads.get(Hh)
                    if not h_reads or not any(a[1] != b[1] for a in w_reads for b in h_reads):
                        continue
                    h = Hypothesis(W, Hh, B, L, 1, enc, declared_end,
                                   _fields(w_reads, h_reads, depths[B], data, B), "generic")
                    key = hypothesis_key(h)
                    if key in found:
                        continue
                    stop = budget.charge()
                    if stop:
                        return GenericOutcome(tuple(found.values()), stop)
                    v = check_closure(h, data)
                    if v.ok:
                        found[key] = (h, v)
                    else:
                        on_reject(h, v)
    return GenericOutcome(tuple(found.values()), None)
