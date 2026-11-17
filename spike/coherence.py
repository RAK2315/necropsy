"""Format-agnostic plausibility scoring for a guessed binary structure.

score() knows nothing about any specific file format. It looks at a dict of
guessed fields and asks whether the numbers could plausibly describe an image.
"""

import math

_VALID_DEPTHS = {1, 4, 8, 16, 24, 32}
_MAX_DIM = 10000


def _int(value):
    """Return value if it is a genuine int (not bool), else None."""
    if type(value) is int:
        return value
    return None


def _dimension_score(w, h):
    if w is None or h is None:
        return None
    ok = sum(1 for d in (w, h) if 0 < d < _MAX_DIM)
    return ok / 2.0


def _depth_score(bpp):
    if bpp is None:
        return None
    return 1.0 if bpp in _VALID_DEPTHS else 0.0


def _size_score(w, h, bpp, data_size, remaining):
    expected = None
    if w is not None and h is not None and bpp is not None:
        if 0 < w < _MAX_DIM and 0 < h < _MAX_DIM and 0 < bpp <= 64:
            expected = ((w * bpp + 7) // 8) * h

    declared = data_size if data_size is not None and data_size > 0 else expected
    pairs = []
    if expected is not None and data_size is not None:
        pairs.append((expected, data_size))
    if declared is not None and remaining is not None:
        pairs.append((declared, remaining))
    if not pairs:
        return None

    ratios = []
    for a, b in pairs:
        if a <= 0 or b <= 0:
            ratios.append(0.0)
        else:
            ratios.append(min(a, b) / max(a, b))
    return sum(ratios) / len(ratios)


def _aspect_score(w, h):
    if w is None or h is None or w <= 0 or h <= 0:
        return None
    ratio = max(w, h) / min(w, h)
    if ratio <= 4:
        return 1.0
    # Decays logarithmically from 1.0 at 4:1 to 0.0 at 100:1.
    return max(0.0, 1.0 - math.log(ratio / 4) / math.log(25))


def score(fields: dict) -> float:
    """Judge how plausible a guessed image structure is, from 0.0 to 1.0.

    Recognised keys (all optional, ints only; anything else is ignored):
      width, height, bit_depth, data_size, remaining_bytes

    Heuristics, each scored 0..1 and averaged over those that apply:

    - Dimensions: width and height are positive integers under 10000.
      Real images are never zero, negative or absurdly large; garbage
      offsets usually produce exactly those values.
    - Bit depth: must be one of {1, 4, 8, 16, 24, 32}, the depths used
      in practice. A random byte rarely lands on one of these.
    - Data size: the pixel data implied by width x height x depth (rows
      padded to whole bytes) should agree with any declared data size and
      with the bytes actually left in the file. Scored as min/max ratio,
      so compression or trailing data costs partial credit, not everything.
    - Aspect ratio: up to 4:1 is fully plausible; beyond that the score
      decays logarithmically, reaching 0 at 100:1.

    Returns 0.0 if no heuristic applies. Never raises.
    """
    try:
        if not isinstance(fields, dict):
            return 0.0
        w = _int(fields.get("width"))
        h = _int(fields.get("height"))
        bpp = _int(fields.get("bit_depth"))
        data_size = _int(fields.get("data_size"))
        remaining = _int(fields.get("remaining_bytes"))

        parts = [
            _dimension_score(w, h),
            _depth_score(bpp),
            _size_score(w, h, bpp, data_size, remaining),
            _aspect_score(w, h),
        ]
        parts = [p for p in parts if p is not None]
        if not parts:
            return 0.0
        result = sum(parts) / len(parts)
        if not (0.0 <= result <= 1.0):
            return 0.0
        return float(result)
    except Exception:
        return 0.0
