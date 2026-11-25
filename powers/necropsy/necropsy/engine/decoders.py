"""Stream decoders for the closure gate.

Every decoder returns a DecodeResult(status, data, consumed_to, detail) and never raises.
Status is one of ok, overrun, underrun, unconsumed, malformed, above_maxval.
consumed_to is the index of the first byte not consumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STATUSES = ("ok", "overrun", "underrun", "unconsumed", "malformed", "above_maxval")

# ASCII whitespace of the PNM format: space, tab, LF, VT, FF, CR.
_WS = frozenset((0x20, 0x09, 0x0A, 0x0B, 0x0C, 0x0D))
_HASH = 0x23
_LF = 0x0A
_CR = 0x0D
_DIGIT_0 = 0x30
_DIGIT_9 = 0x39
# A token of more than this many digits after leading zeros exceeds every valid maxval (65535).
_MAX_SIGNIFICANT_DIGITS = 5
_MAX_MAXVAL = 65535


@dataclass(frozen=True)
class DecodeResult:
    status: str
    data: Optional[bytes]
    consumed_to: int
    detail: str = ""


def _fail(status: str, consumed_to: int, detail: str = "") -> DecodeResult:
    return DecodeResult(status, None, consumed_to, detail)


def pnm_text_decode(data, start, end, width, height, bit_depth, maxval, max_output_bytes) -> DecodeResult:
    """Decode plain-text PNM numbers (P1, P2, P3) in data[start:end]. Never raises."""
    try:
        return _pnm_text_decode(data, start, end, width, height, bit_depth, maxval, max_output_bytes)
    except Exception as exc:  # last line of defence; inner code is written not to raise
        return _fail("underrun", start if isinstance(start, int) else 0, "internal error: " + type(exc).__name__)


def _pnm_text_decode(data, start, end, width, height, bit_depth, maxval, max_output_bytes) -> DecodeResult:
    for v in (start, end, width, height, bit_depth, maxval, max_output_bytes):
        if not isinstance(v, int) or isinstance(v, bool):
            return _fail("underrun", 0, "non-integer argument")
    if start < 0 or end > len(data) or start > end or max_output_bytes < 0:
        return _fail("underrun", start, "invalid arguments")
    if width < 0 or height < 0 or maxval < 0 or maxval > _MAX_MAXVAL or bit_depth not in (1, 8, 16, 24, 48):
        return _fail("underrun", start, "invalid layout parameters")

    per_pixel = 3 if bit_depth in (24, 48) else 1
    total = width * height * per_pixel  # N numbers expected
    packed = bit_depth == 1
    sample_bytes = 2 if maxval > 255 else 1

    out = bytearray()
    count = 0  # numbers written
    i = start

    while i < end:
        b = data[i]
        if b in _WS:
            i += 1
            continue
        if b == _HASH:
            i += 1
            while i < end and data[i] != _LF and data[i] != _CR:
                i += 1
            continue

        # A number (or, in P1, a digit) or a stray byte starts at i.
        if count >= total:
            return _fail("unconsumed", i, "stray data after the last number at offset %d" % i)

        if packed:
            if not (_DIGIT_0 <= b <= _DIGIT_9):
                return _fail("malformed", i, "byte 0x%02x at offset %d is not 0, 1, whitespace or a comment" % (b, i))
            value = b - _DIGIT_0
            token_end = i + 1
            token_start = i
        else:
            token_start = i
            j = i
            while j < end and data[j] not in _WS and data[j] != _HASH:
                j += 1
            token_end = j
            token = data[token_start:token_end]
            if not all(_DIGIT_0 <= c <= _DIGIT_9 for c in token):
                return _fail("malformed", token_start, "token at offset %d is not a decimal number" % token_start)
            significant = token.lstrip(b"0")
            if len(significant) > _MAX_SIGNIFICANT_DIGITS:
                return _fail("above_maxval", token_end,
                             "value %s at offset %d is above maximum %d" % (significant.decode("ascii"), token_start, maxval))
            value = int(significant) if significant else 0

        if value > maxval:
            return _fail("above_maxval", token_end,
                         "value %d at offset %d is above maximum %d" % (value, token_start, maxval))

        if packed:
            col = count % width  # total > count implies width > 0
            if col % 8 == 0:
                if len(out) + 1 > max_output_bytes:
                    return _fail("overrun", token_end, "write at offset %d would pass %d bytes" % (token_start, max_output_bytes))
                out.append(0)
            if value:
                out[-1] |= 0x80 >> (col % 8)
        else:
            if sample_bytes > max_output_bytes - len(out):
                return _fail("overrun", token_end, "write at offset %d would pass %d bytes" % (token_start, max_output_bytes))
            if sample_bytes == 2:
                out.append(value >> 8)
                out.append(value & 0xFF)
            else:
                out.append(value)
        count += 1
        i = token_end

    if count < total:
        return _fail("underrun", end, "region ended after %d of %d numbers" % (count, total))
    if len(out) != max_output_bytes:
        return _fail("underrun", end, "output is %d bytes, expected %d" % (len(out), max_output_bytes))
    return DecodeResult("ok", bytes(out), end, "")


# Requirement 2.13: the largest decoded size a decoder encoding may be asked for (8 MiB).
DECODE_CAP = 8 * 1024 * 1024


def _run_pnm_text(data, start, end, h, max_output_bytes) -> DecodeResult:
    return pnm_text_decode(data, start, end, h.width, h.height, h.bit_depth,
                           h.maxval if h.maxval is not None else 0, max_output_bytes)


# Data read by the closure gate: hypothesis encoding -> adapter(data, start, end, h, max_output_bytes).
DECODERS = {
    "pnm_text": _run_pnm_text,
}

# Requirement 2.12: decoder state -> closure rejection reason.
STATUS_REASONS = {
    "overrun": "decoder_overrun",
    "underrun": "decoder_underrun",
    "unconsumed": "decoder_unconsumed",
    "malformed": "decoder_malformed",
    "above_maxval": "sample_above_maxval",
}


def rle_tga_decode(data, start, end, pixel_bytes, max_output_bytes) -> DecodeResult:
    """Decode TGA run-length packets (image types 9, 10, 11) in data[start:end]. Never raises.

    Packet header h (1 byte): h >= 0x80 is a run, (h & 0x7F) + 1 copies of the next
    pixel_bytes bytes; h < 0x80 is raw, (h + 1) * pixel_bytes bytes follow as they are.
    The packets are one continuous stream; a packet may cross the end of a row (Requirement 5.4).
    """
    try:
        return _rle_tga_decode(data, start, end, pixel_bytes, max_output_bytes)
    except Exception as exc:  # last line of defence; inner code is written not to raise
        return _fail("underrun", start if isinstance(start, int) else 0, "internal error: " + type(exc).__name__)


def _rle_tga_decode(data, start, end, pixel_bytes, max_output_bytes) -> DecodeResult:
    for v in (start, end, pixel_bytes, max_output_bytes):
        if not isinstance(v, int) or isinstance(v, bool):
            return _fail("underrun", 0, "non-integer argument")
    if start < 0 or end > len(data) or start > end or max_output_bytes < 0 or pixel_bytes < 1:
        return _fail("underrun", start, "invalid arguments")

    out = bytearray()
    i = start
    while len(out) < max_output_bytes and i < end:
        h = data[i]
        if h >= 0x80:
            packet_end = i + 1 + pixel_bytes
            if packet_end > end:
                return _fail("underrun", end, "region ended inside the run packet at offset %d" % i)
            n = ((h & 0x7F) + 1) * pixel_bytes
            if n > max_output_bytes - len(out):
                return _fail("overrun", packet_end, "run at offset %d would pass %d bytes" % (i, max_output_bytes))
            out += data[i + 1:packet_end] * ((h & 0x7F) + 1)
        else:
            n = (h + 1) * pixel_bytes
            packet_end = i + 1 + n
            if packet_end > end:
                return _fail("underrun", end, "region ended inside the raw packet at offset %d" % i)
            if n > max_output_bytes - len(out):
                return _fail("overrun", packet_end, "raw packet at offset %d would pass %d bytes" % (i, max_output_bytes))
            out += data[i + 1:packet_end]
        i = packet_end

    if len(out) < max_output_bytes:
        return _fail("underrun", end, "output is %d bytes, expected %d" % (len(out), max_output_bytes))
    if i < end:
        return _fail("unconsumed", i, "%d bytes remain after the output is full" % (end - i))
    return DecodeResult("ok", bytes(out), end, "")
