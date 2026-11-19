"""Trailer registry: fixed-length footers that end the data region early."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrailerEntry:
    name: str
    length: int
    marker: int
    applies_to: frozenset


TRAILER_REGISTRY = (
    TrailerEntry("pcx_palette_256", 769, 0x0C, frozenset({"pcx", "generic"})),
)


def match_trailer(data, header_size, origin, registry=TRAILER_REGISTRY):
    """Return (trailer_start, name). With no match, (len(data), None). Never raises."""
    try:
        n = len(data)
    except Exception:
        return 0, None
    try:
        for e in registry:
            if (
                origin in e.applies_to
                and n - e.length >= header_size
                and data[n - e.length] == e.marker
            ):
                return n - e.length, e.name
    except Exception:
        pass
    return n, None
