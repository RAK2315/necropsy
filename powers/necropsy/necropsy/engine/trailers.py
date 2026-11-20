"""Trailer registry: fixed-length footers that end the data region early."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


import struct


@dataclass(frozen=True)
class DeclaredArea:
    """A nested area whose start is a declared offset. Inner offsets are (name, position from area start, fmt)."""
    base: str
    size_at: int
    size_fmt: str
    min_size: int
    offsets: tuple


@dataclass(frozen=True)
class TrailerEntry:
    name: str
    length: int
    signature: bytes
    signature_offset: int
    applies_to: frozenset
    declared_offsets: tuple = ()  # (name, position from trailer start, fmt)
    declared_area: Optional[DeclaredArea] = None


TRAILER_REGISTRY = (
    TrailerEntry("pcx_palette_256", 769, b"\x0c", 0, frozenset({"pcx", "generic"})),
    TrailerEntry(
        "tga2_footer", 26, b"TRUEVISION-XFILE.\x00", 8, frozenset({"tga", "generic"}),
        declared_offsets=(("extension_area_offset", 0, "<I"), ("developer_area_offset", 4, "<I")),
        declared_area=DeclaredArea(
            "extension_area_offset", 0, "<H", 495,
            (("colour_correction_offset", 482, "<I"),
             ("postage_stamp_offset", 486, "<I"),
             ("scan_line_offset", 490, "<I")),
        ),
    ),
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
                and data[n - e.length + e.signature_offset : n - e.length + e.signature_offset + len(e.signature)] == e.signature
            ):
                return n - e.length, e.name
    except Exception:
        pass
    return n, None


def _evaluate_trailer(data, header_size, origin, registry):
    """Shared evaluation: return (data_end, trailer_name, error, detail).

    error is None or "field_out_of_bounds"; detail is "" unless error is set.
    Never raises. All declared-offset reads are little-endian and bounds-checked.
    """
    try:
        n = len(data)
        start, name = match_trailer(data, header_size, origin, registry)
        if name is None:
            return n, None, None, ""
        e = next(x for x in registry if x.name == name)
        F = start
        L = header_size

        def fail(detail):
            return F, name, "field_out_of_bounds", detail

        if not e.declared_offsets:
            return F, name, None, ""

        def u(fmt, at):
            if at < 0 or at + struct.calcsize(fmt) > n:
                return None
            return struct.unpack_from(fmt, data, at)[0]

        decl = {}
        for nm, pos, fmt in e.declared_offsets:
            v = u(fmt, F + pos)
            if v is None:
                return fail(f"header_length {L}: {nm} unreadable")
            decl[nm] = v
        ends = [F]

        def take(v):
            if v == 0:
                return True
            if not (header_size <= v < F):
                return False
            ends.append(v)
            return True

        def range_detail(nm, v):
            return f"header_length {L}: {nm} = {v} not in [{L}, {F})"

        for nm, v in decl.items():
            if not take(v):
                return fail(range_detail(nm, v))
        a = e.declared_area
        if a is not None and decl.get(a.base, 0) != 0:
            E = decl[a.base]
            size = u(a.size_fmt, E + a.size_at)
            if size is None or size < a.min_size or E + size > F:
                shown = "unreadable" if size is None else size
                return fail(f"header_length {L}: extension area at {E} has size {shown}; "
                            f"requires size >= {a.min_size} and {E} + size <= {F}")
            for nm, pos, fmt in a.offsets:
                v = u(fmt, E + pos)
                if v is None:
                    return fail(f"header_length {L}: {nm} unreadable")
                if not take(v):
                    return fail(range_detail(nm, v))
        return min(ends), name, None, ""
    except Exception:
        return (len(data) if hasattr(data, "__len__") else 0), None, None, ""


def trailer_data_end_detail(data, header_size, origin, registry=TRAILER_REGISTRY):
    """Return (data_end, trailer_name, error, detail). Same evaluation as trailer_data_end."""
    return _evaluate_trailer(data, header_size, origin, registry)


def trailer_data_end(data, header_size, origin, registry=TRAILER_REGISTRY):
    """Return (data_end, trailer_name, error); error is None or "field_out_of_bounds".

    Never raises. When error is set, data_end is the trailer start and callers
    must not use it.
    """
    return _evaluate_trailer(data, header_size, origin, registry)[:3]