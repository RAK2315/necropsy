"""Row coherence heuristic (Requirement 11).

Standard library only. No network calls. Never raises.
"""

from __future__ import annotations

import random
from typing import Iterable, Optional

COHERENCE_METHOD = "row_mad_ratio"
COHERENCE_SIZE_LIMIT = 262_144

_MAX_PAIRS = 1024


def _before(i: int, h: int) -> int:
    """Number of pairs (a, b), a < b, whose first row a is before row i."""
    return i * (2 * h - i - 1) // 2


def pair_at(k: int, h: int) -> tuple[int, int]:
    """Return the k-th pair (i, j), i < j, in lexicographic order, in O(log h)."""
    lo, hi = 0, h - 2  # largest i with before(i) <= k
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _before(mid, h) <= k:
            lo = mid
        else:
            hi = mid - 1
    return lo, lo + 1 + k - _before(lo, h)


def _score(decoded: bytes, height: int, row_stride: int) -> tuple[Optional[float], str]:
    if height * row_stride > COHERENCE_SIZE_LIMIT:
        return None, "not_computed"
    if height < 2 or row_stride < 1 or len(decoded) < height * row_stride:
        return None, "unscorable"
    rows = [decoded[i * row_stride:(i + 1) * row_stride] for i in range(height)]

    def mad(a: bytes, b: bytes) -> float:
        return sum(abs(x - y) for x, y in zip(a, b)) / row_stride

    adjacent = sum(mad(rows[i], rows[i + 1]) for i in range(height - 1)) / (height - 1)
    p = height * (height - 1) // 2
    ks = range(p) if p <= _MAX_PAIRS else random.Random(0).sample(range(p), _MAX_PAIRS)
    pairs = [pair_at(k, height) for k in ks]
    baseline = sum(mad(rows[i], rows[j]) for i, j in pairs) / len(pairs)
    if baseline == 0:
        return None, "unscorable"
    return adjacent / baseline, "scored"


def row_coherence(decoded: bytes, height: int, row_stride: int) -> tuple[Optional[float], str]:
    """Row coherence score and status: (score, "scored"), or (None, "unscorable" | "not_computed").

    A lower score means more coherent. The score is adjacent-row mean absolute
    difference divided by the mean over all (or 1,024 sampled) row pairs.

    Heuristic only. Never a gate, never promotes, never orders.

    Known failure modes:
    1. Narrower strides score better on smooth images: at stride 1 the "rows"
       are horizontal neighbours.
    2. Identical bytes at an identical stride, split into different bit depths
       (8x8 at 8 bpp and 64x8 at 1 bpp), score identically.
    3. A header can absorb whole rows: a candidate missing the top rows of the
       true image scores close to it.
    """
    try:
        return _score(decoded, height, row_stride)
    except Exception:
        return None, "unscorable"


def coherence_gap(scores: Iterable[Optional[float]]) -> Optional[float]:
    """(second - first) / second over the two lowest scores, for information only.

    None when fewer than two scores are given or the second-lowest is 0.
    """
    try:
        vals = sorted(s for s in scores if s is not None)
        if len(vals) < 2:
            return None
        first, second = vals[0], vals[1]
        if second == 0:
            return None
        return (second - first) / second
    except Exception:
        return None
