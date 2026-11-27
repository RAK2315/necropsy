"""Closure gate primitives: row stride and the PCX run-length decoder."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional


def row_stride(width: int, bit_depth: int, row_alignment: int) -> int:
    """round_up(ceil(width * bit_depth / 8), row_alignment), integer arithmetic only."""
    raw = -(-(width * bit_depth) // 8)
    return -(-raw // row_alignment) * row_alignment


def hypothesis_row_stride(h) -> int:
    """Declared row_bytes when set, otherwise the derived row stride."""
    if h.row_bytes is not None:
        return h.row_bytes
    return row_stride(h.width, h.bit_depth, h.row_alignment)


@dataclass(frozen=True)
class RleResult:
    status: str  # ok | overrun | underrun | unconsumed
    data: Optional[bytes]
    consumed_to: int


def rle_pcx_decode(data: bytes, start: int, end: int, max_output_bytes: int) -> RleResult:
    """Decode PCX RLE in data[start:end] to exactly max_output_bytes. Never raises."""
    try:
        if start < 0 or end > len(data) or start > end or max_output_bytes < 0:
            return RleResult("underrun", None, start)
        out = bytearray()
        i = start
        while i < end and len(out) < max_output_bytes:
            b = data[i]
            i += 1
            if b >= 0xC0:
                if i >= end:
                    return RleResult("underrun", None, i)  # marker is last byte
                run = b & 0x3F
                v = data[i]
                i += 1
                if run > max_output_bytes - len(out):
                    return RleResult("overrun", None, i)  # checked before writing
                out += bytes((v,)) * run
            else:
                out.append(b)
        if len(out) != max_output_bytes:
            return RleResult("underrun", None, i)
        if i != end:
            return RleResult("unconsumed", None, i)
        return RleResult("ok", bytes(out), i)
    except Exception:
        return RleResult("underrun", None, start if isinstance(start, int) else 0)


def rle_pcx_output_length(data: bytes, start: int, end: int) -> Optional[int]:
    """Count the decoded length of data[start:end] without allocating output.

    Returns None if a final run marker is truncated or the range is invalid.
    """
    try:
        if start < 0 or end > len(data) or start > end:
            return None
        n = 0
        i = start
        while i < end:
            b = data[i]
            i += 1
            if b >= 0xC0:
                if i >= end:
                    return None
                n += b & 0x3F
                i += 1
            else:
                n += 1
        return n
    except Exception:
        return None


@dataclass(frozen=True)
class ClosureVerdict:
    ok: bool
    reason: str
    discrepancy: Optional[int]
    decoded: Optional[bytes]
    data_start: Optional[int]
    data_end: Optional[int]
    trailer: Optional[str]
    detail: str = ""


def _reject(reason: str, discrepancy: Optional[int] = None) -> ClosureVerdict:
    return ClosureVerdict(False, reason, discrepancy, None, None, None, None)


def _accept(decoded: bytes, start: int, end: int, trailer: Optional[str]) -> ClosureVerdict:
    return ClosureVerdict(True, "", None, decoded, start, end, trailer)


REPORT_ONLY_FIELDS = frozenset({"color_map"})   # declared and reported; never part of the structure arithmetic


def structural_fields(h):
    """The header fields the Requirement 12 check compares with the data region."""
    return tuple(f for f in h.fields if f.name not in REPORT_ONLY_FIELDS)


def readings(h, data: bytes) -> tuple:
    """Readings of a hypothesis: the trailer reading first, then the end-of-file reading.

    A matched trailer is a reading, not a fact (Requirement 1.17). A hypothesis with a
    declared data_end, or with no matching registry entry, has one reading. Never
    raises and never ranks.
    """
    try:
        from dataclasses import replace
        from .trailers import match_trailer
        if h.data_end is not None:
            return (h,)
        _, name = match_trailer(data, h.header_size, h.probe_name)
        if name is None:
            return (h,)
        return (h, replace(h, data_end=len(data)))
    except Exception:
        return (h,)


def _first_sample_above(data: bytes, start: int, end: int, maxval: int, size: int):
    """First (offset, value) of a 1-byte or big-endian 2-byte sample above maxval, else None.

    Allocates nothing sized from maxval.
    """
    if size == 1:
        if maxval >= 255:
            return None
        for i in range(start, end):
            if data[i] > maxval:
                return i, data[i]
        return None
    if maxval >= 65535:
        return None
    for i in range(start, end - 1, 2):
        v = (data[i] << 8) | data[i + 1]
        if v > maxval:
            return i, v
    return None


def _detail_reject(reason: str, detail: str, discrepancy: Optional[int] = None) -> ClosureVerdict:
    return ClosureVerdict(False, reason, discrepancy, None, None, None, None, detail)


def _decode_range(h, data: bytes, i: int, start: int, end: int, unit: int):
    """Decode one range of a compressed hypothesis to exactly `unit` bytes.

    Returns (bytes, None) or (None, ClosureVerdict). Requirement 2.13: unit is capped.
    """
    from .decoders import DECODE_CAP, DECODERS, STATUS_REASONS
    run = DECODERS.get(h.encoding)
    if run is None:
        return None, _reject("unsupported_encoding")
    if unit > DECODE_CAP:
        return None, _detail_reject("degenerate_hypothesis",
                                    "range %d expects %d decoded bytes, above the cap %d" % (i, unit, DECODE_CAP))
    r = run(data, start, end, h, unit)
    if r.status == "ok":
        return r.data, None
    return None, _detail_reject(STATUS_REASONS.get(r.status, "internal_error"),
                                "range %d [%d, %d): %s" % (i, start, end, r.detail))


def _check_ranges(h, data: bytes) -> ClosureVerdict:
    """Strips with encoding none (Requirements 7.5 to 7.8, 7.10 to 7.12).

    Order: bounds per range, Requirement 12 per range, pairwise disjoint, unit count,
    then each range in order. Allocates only from the file's own bytes, never from the
    declared strip count.
    """
    ranges = h.ranges
    n = len(ranges)
    for i, rg in enumerate(ranges):
        start, end = rg
        if not (0 <= start <= end <= len(data)):
            return _detail_reject("field_out_of_bounds",
                                  "range %d [%d, %d) lies outside the %d-byte file" % (i, start, end, len(data)))
    for i, (start, end) in enumerate(ranges):
        if end <= start:
            continue
        for fr in structural_fields(h):
            try:
                f_end = fr.offset + struct.calcsize(fr.fmt)
            except Exception:
                return _reject("degenerate_hypothesis")
            if fr.offset < end and start < f_end:
                return _detail_reject(
                    "degenerate_hypothesis",
                    "range %d [%d, %d) overlaps header field %s [%d, %d)" % (i, start, end, fr.name, fr.offset, f_end))
    spans = sorted((s, e, i) for i, (s, e) in enumerate(ranges) if e > s)
    for (s1, e1, i1), (s2, e2, i2) in zip(spans, spans[1:]):
        if s2 < e1:
            return _detail_reject("degenerate_hypothesis",
                                  "ranges %d [%d, %d) and %d [%d, %d) overlap" % (i1, s1, e1, i2, s2, e2))
    if h.tile is not None:
        return _check_tiles(h, data)
    rps = h.rows_per_strip
    if rps is None or rps <= 0:
        return _detail_reject("degenerate_hypothesis", "ranges need rows_per_strip > 0 and no tile")
    want = -(-h.height // rps)
    if n != want:
        return _detail_reject("degenerate_hypothesis",
                              "%d ranges declared, ceil(%d / %d) = %d strips expected" % (n, h.height, rps, want))
    stride = hypothesis_row_stride(h)
    out = bytearray()
    if h.encoding != "none":
        from .decoders import DECODE_CAP, DECODERS
        if h.encoding not in DECODERS:
            return _reject("unsupported_encoding")
        if stride * h.height > DECODE_CAP:
            return _detail_reject("degenerate_hypothesis",
                                  "assembled image of %d bytes is above the cap of %d" % (stride * h.height, DECODE_CAP))
        for i, (start, end) in enumerate(ranges):
            rows = min(rps, h.height - i * rps)
            piece, bad = _decode_range(h, data, i, start, end, rows * stride)
            if bad is not None:
                return bad
            out += piece
        return _accept(bytes(out), min(s for s, _ in ranges), max(e for _, e in ranges), None)
    for i, (start, end) in enumerate(ranges):
        rows = min(rps, h.height - i * rps)
        unit = rows * stride
        if end - start != unit:
            return _detail_reject(
                "arithmetic_mismatch",
                "range %d [%d, %d) holds %d bytes, its %d rows need %d" % (i, start, end, end - start, rows, unit),
                (end - start) - unit)
        out += data[start:end]
    return _accept(bytes(out), min(s for s, _ in ranges), max(e for _, e in ranges), None)


def _check_tiles(h, data: bytes) -> ClosureVerdict:
    """Tiles with encoding none (Requirements 7.9, 7.10 to 7.12, 9.6).

    Called after bounds, Requirement 12 and overlap checks. The assembled image is
    stride x height bytes; that size is checked against DECODE_CAP before the
    bytearray is allocated, and nothing is sized from the declared tile count.
    """
    from .decoders import DECODE_CAP
    ranges = h.ranges
    n = len(ranges)
    tw, tl = h.tile
    if tw <= 0 or tl <= 0:
        return _detail_reject("degenerate_hypothesis", "tile %d x %d must be positive" % (tw, tl))
    if (tw * h.bit_depth) % 8 != 0:
        return _detail_reject("degenerate_hypothesis",
                              "tile width %d at %d bits does not start a column on a byte" % (tw, h.bit_depth))
    across = -(-h.width // tw)
    down = -(-h.height // tl)
    if n != across * down:
        return _detail_reject("degenerate_hypothesis",
                              "%d ranges declared, %d x %d = %d tiles expected" % (n, across, down, across * down))
    if h.encoding != "none":
        from .decoders import DECODERS
        if h.encoding not in DECODERS:
            return _reject("unsupported_encoding")
    stride = hypothesis_row_stride(h)
    total = stride * h.height
    if total > DECODE_CAP:
        return _detail_reject("degenerate_hypothesis",
                              "assembled image of %d bytes is above the cap of %d" % (total, DECODE_CAP))
    tile_row = (tw * h.bit_depth) // 8
    unit = tile_row * tl
    tiles = []
    for i, (start, end) in enumerate(ranges):
        if h.encoding != "none":
            piece, bad = _decode_range(h, data, i, start, end, unit)
            if bad is not None:
                return bad
            tiles.append(piece)
        elif end - start != unit:
            return _detail_reject(
                "arithmetic_mismatch",
                "range %d [%d, %d) holds %d bytes, its tile needs %d" % (i, start, end, end - start, unit),
                (end - start) - unit)
    out = bytearray(total)
    for i, (start, _end) in enumerate(ranges):
        src_buf, start = (tiles[i], 0) if tiles else (data, start)
        x = (i % across) * tile_row
        y = (i // across) * tl
        copy = min(tile_row, stride - x)
        if copy <= 0:
            continue
        for r in range(min(tl, h.height - y)):
            src = start + r * tile_row
            dst = (y + r) * stride + x
            out[dst:dst + copy] = src_buf[src:src + copy]
    return _accept(bytes(out), min(s for s, _ in ranges), max(e for _, e in ranges), None)


def check_closure(h, data: bytes) -> ClosureVerdict:
    """Closure gate: decode [header_size, data_end) and require exact length and full consumption."""
    try:
        if (h.width <= 0 or h.height <= 0 or h.bit_depth <= 0
                or h.row_alignment not in (1, 2, 4)
                or h.header_size < 0 or h.header_size > len(data)):
            return _reject("degenerate_hypothesis")
        expected = hypothesis_row_stride(h) * h.height
        if h.row_bytes is not None:
            # Requirement 6.4: a declared scanline must be able to hold the width.
            planes = h.planes
            if planes < 1 or h.row_bytes <= 0 or h.bit_depth % planes != 0:
                return ClosureVerdict(
                    False, "degenerate_hypothesis", None, None, None, None, None,
                    "row_bytes %s with bit_depth %d is not a whole number of bits per plane for %d planes"
                    % (h.row_bytes, h.bit_depth, planes))
            plane_bytes = -(-(h.width * (h.bit_depth // planes)) // 8)
            if h.row_bytes < planes * plane_bytes:
                return ClosureVerdict(
                    False, "degenerate_hypothesis", None, None, None, None, None,
                    "row_bytes %d is below planes x ceil(width x bits per plane / 8) = %d"
                    % (h.row_bytes, planes * plane_bytes))
        if h.ranges:
            return _check_ranges(h, data)
        if h.data_end is not None:
            if h.data_end > len(data) or h.data_end < h.header_size:
                return _reject("field_out_of_bounds")
            end, trailer = h.data_end, None
        else:
            from .trailers import trailer_data_end
            end, trailer, t_err = trailer_data_end(data, h.header_size, h.probe_name)
            if t_err:
                return _reject(t_err)
        # Requirement 12: header fields and the data region are disjoint
        # (half-open ranges). A malformed fmt cannot raise out of here.
        if end > h.header_size:
            for fr in structural_fields(h):
                try:
                    f_end = fr.offset + struct.calcsize(fr.fmt)
                except Exception:
                    return _reject("degenerate_hypothesis")
                if fr.offset < end and h.header_size < f_end:
                    return _reject("degenerate_hypothesis")
        if h.encoding == "none":
            if end - h.header_size == expected:
                if h.maxval is not None:
                    bad = _first_sample_above(data, h.header_size, end, h.maxval,
                                              2 if h.bit_depth in (16, 48) else 1)
                    if bad is not None:
                        off, val = bad
                        return ClosureVerdict(
                            False, "sample_above_maxval", None, None, None, None, None,
                            "sample at offset %d is %d, above the declared maximum %d"
                            % (off, val, h.maxval))
                return _accept(bytes(data[h.header_size:end]), h.header_size, end, trailer)
            return _reject("arithmetic_mismatch", (end - h.header_size) - expected)
        if h.encoding == "rle_pcx":
            r = rle_pcx_decode(data, h.header_size, end, expected)
            if r.status == "ok":
                return _accept(r.data, h.header_size, end, trailer)
            return _reject("decoder_" + r.status)
        from .decoders import DECODE_CAP, DECODERS, STATUS_REASONS
        run = DECODERS.get(h.encoding)
        if run is not None:
            if expected > DECODE_CAP:
                return ClosureVerdict(
                    False, "degenerate_hypothesis", None, None, None, None, None,
                    "expected decoded size %d is above the cap %d" % (expected, DECODE_CAP))
            r = run(data, h.header_size, end, h, expected)
            if r.status == "ok":
                return _accept(r.data, h.header_size, end, trailer)
            return ClosureVerdict(False, STATUS_REASONS.get(r.status, "internal_error"),
                                  None, None, None, None, None, r.detail)
        return _reject("unsupported_encoding")
    except Exception:
        return _reject("internal_error")
