"""PCX parser written from requirements.md and design.md only.

parse(data) never raises. On success it returns a dict with ok=True; on any
failure it returns {"ok": False, "error": {"code": ..., "message": ...}}.
"""
import struct

# (name, offset, struct format): requirements.md, Requirement 2, items 1-9.
_FIELDS = (
    ("manufacturer", 0x0000, "B"),
    ("encoding", 0x0002, "B"),
    ("bit_depth", 0x0003, "B"),
    ("xmin", 0x0004, "<H"),
    ("ymin", 0x0006, "<H"),
    ("xmax", 0x0008, "<H"),
    ("ymax", 0x000A, "<H"),
    ("planes", 0x0041, "B"),
    ("bytes_per_line", 0x0042, "<H"),
)
_MANUFACTURER = 10  # Requirement 1.1
_DATA_START = 128  # Requirement 3.2
_ROW_ALIGNMENT = 1  # Requirement 3.1
_TRAILER_LEN = 769  # Requirement 3.4
_TRAILER_SIG = 0x0C  # Requirement 3.4
_ENCODINGS = {0: "none", 1: "rle_pcx"}  # Requirement 3.5


class _Fail(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def _error(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def _rle_decode(region, expected):
    """Requirement 3.7."""
    out = bytearray()
    i = 0
    n = len(region)
    while len(out) < expected and i < n:
        b = region[i]
        i += 1
        if b >= 0xC0:
            if i >= n:
                raise _Fail("rle_truncated_run", "run marker is the last byte of the data region")
            count = b & 0x3F
            v = region[i]
            i += 1
            if len(out) + count > expected:
                raise _Fail("rle_overrun", "run exceeds row_stride x height bytes")
            if count:
                out.extend(bytes((v,)) * count)
        else:
            out.append(b)
    if len(out) < expected:
        raise _Fail("rle_short", "output shorter than row_stride x height at end of data region")
    if i < n:
        raise _Fail("rle_unconsumed", "unread bytes remain after output is complete")
    return bytes(out)


def _parse(data):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise _Fail("not_bytes", "input is not a bytes-like object")
    data = bytes(data)
    n = len(data)
    if n < _DATA_START:
        raise _Fail("truncated_header", "file is shorter than the 128-byte header")

    values = {}
    fields = []
    for name, offset, fmt in _FIELDS:
        value = struct.unpack_from(fmt, data, offset)
        values[name] = value[0]
        fields.append((name, offset, fmt, value))

    if values["manufacturer"] != _MANUFACTURER:
        raise _Fail("bad_signature", "manufacturer is not 10")

    width = values["xmax"] - values["xmin"] + 1
    height = values["ymax"] - values["ymin"] + 1
    if width < 1 or height < 1:
        raise _Fail("bad_bounds", "bounds give a non-positive width or height")
    bit_depth = values["bit_depth"]

    enc = _ENCODINGS.get(values["encoding"])
    if enc is None:
        raise _Fail("unknown_encoding", "encoding value %d is not 0 or 1" % values["encoding"])

    data_start = _DATA_START
    data_end = n
    trailer = None
    t = n - _TRAILER_LEN
    if t >= data_start and data[t] == _TRAILER_SIG:
        trailer = "pcx_palette_256"
        data_end = t

    raw = -(-(width * bit_depth) // 8)
    row_stride = -(-raw // _ROW_ALIGNMENT) * _ROW_ALIGNMENT
    expected = row_stride * height

    region = data[data_start:data_end]
    if enc == "none":
        if len(region) != expected:
            raise _Fail("closure_failed", "data region length != row_stride x height")
        pixels = region
    else:
        pixels = _rle_decode(region, expected)

    return {
        "ok": True,
        "fields": fields,
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "row_alignment": _ROW_ALIGNMENT,
        "row_stride": row_stride,
        "encoding": enc,
        "data_start": data_start,
        "data_end": data_end,
        "trailer": trailer,
        "pixels": pixels,
    }


def parse(data):
    try:
        return _parse(data)
    except _Fail as e:
        return _error(e.code, e.message)
    except Exception as e:  # backstop: parse must never raise
        return _error("internal", "%s: %s" % (type(e).__name__, e))
