"""Closure gate primitives: row stride and the PCX run-length decoder."""
from __future__ import annotations

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
