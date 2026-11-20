"""Closure gate primitives: row stride and the PCX run-length decoder."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional


def row_stride(width: int, bit_depth: int, row_alignment: int) -> int:
    """round_up(ceil(width * bit_depth / 8), row_alignment), integer arithmetic only."""
    raw = -(-(width * bit_depth) // 8)
    return -(-raw // row_alignment) * row_alignment


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


def _reject(reason: str, discrepancy: Optional[int] = None) -> ClosureVerdict:
    return ClosureVerdict(False, reason, discrepancy, None, None, None, None)


def _accept(decoded: bytes, start: int, end: int, trailer: Optional[str]) -> ClosureVerdict:
    return ClosureVerdict(True, "", None, decoded, start, end, trailer)


def check_closure(h, data: bytes) -> ClosureVerdict:
    """Closure gate: decode [header_size, data_end) and require exact length and full consumption."""
    try:
        if (h.width <= 0 or h.height <= 0 or h.bit_depth <= 0
                or h.row_alignment not in (1, 2, 4)
                or h.header_size < 0 or h.header_size > len(data)):
            return _reject("degenerate_hypothesis")
        expected = row_stride(h.width, h.bit_depth, h.row_alignment) * h.height
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
            for fr in h.fields:
                try:
                    f_end = fr.offset + struct.calcsize(fr.fmt)
                except Exception:
                    return _reject("degenerate_hypothesis")
                if fr.offset < end and h.header_size < f_end:
                    return _reject("degenerate_hypothesis")
        if h.encoding == "none":
            if end - h.header_size == expected:
                return _accept(bytes(data[h.header_size:end]), h.header_size, end, trailer)
            return _reject("arithmetic_mismatch", (end - h.header_size) - expected)
        if h.encoding == "rle_pcx":
            r = rle_pcx_decode(data, h.header_size, end, expected)
            if r.status == "ok":
                return _accept(r.data, h.header_size, end, trailer)
            return _reject("decoder_" + r.status)
        return _reject("unsupported_encoding")
    except Exception:
        return _reject("internal_error")
