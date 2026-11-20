"""Revision strategies. Each maps a Hypothesis to candidate revisions; never raises."""

from __future__ import annotations

from dataclasses import replace

from .types import Hypothesis


def _safe(fn):
    def wrapper(h: Hypothesis) -> tuple[Hypothesis, ...]:
        try:
            return tuple(fn(h))
        except Exception:
            return ()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_safe
def inclusive_bounds(h: Hypothesis) -> tuple[Hypothesis, ...]:
    if h.bounds is None:
        return ()
    xmin, ymin, xmax, ymax = h.bounds
    return (replace(h, width=xmax - xmin + 1, height=ymax - ymin + 1,
                    revision_path=h.revision_path + ("inclusive_bounds",)),)


@_safe
def rle_pcx(h: Hypothesis) -> tuple[Hypothesis, ...]:
    if h.probe_name != "pcx" or h.encoding != "none":
        return ()
    return (replace(h, encoding="rle_pcx", revision_path=h.revision_path + ("rle_pcx",)),)


@_safe
def row_padding_variants(h: Hypothesis) -> tuple[Hypothesis, ...]:
    return tuple(replace(h, row_alignment=a, revision_path=h.revision_path + ("row_padding_variants",))
                 for a in (2, 4) if a != h.row_alignment)


STRATEGIES = (
    ("inclusive_bounds", inclusive_bounds),
    ("rle_pcx", rle_pcx),
    ("row_padding_variants", row_padding_variants),
)
