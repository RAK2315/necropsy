"""Reference reader: a generic interpreter of necropsy-layout/1.

Contains no knowledge of any specific format. Imports only json, lzma, re, struct and zlib.
Never raises on arbitrary bytes or malformed layouts.
"""
import json
import lzma
import re
import struct
import zlib

_FENCE = re.compile(r"^```[ \t]*necropsy-layout[ \t]*\r?\n(.*?)^```[ \t]*\r?$",
                    re.DOTALL | re.MULTILINE)
_MAX_ENTRIES = 1 << 16


class _Err(Exception):
    pass


def extract_layout(markdown):
    """Return the layout dict from the single necropsy-layout block, or an error string."""
    try:
        blocks = _FENCE.findall(markdown)
        if len(blocks) == 0:
            return "no necropsy-layout block"
        if len(blocks) > 1:
            return "more than one necropsy-layout block"
        layout = json.loads(blocks[0])
        if not isinstance(layout, dict):
            return "layout is not a JSON object"
        return layout
    except Exception as exc:  # malformed input must not raise
        return "invalid layout: " + type(exc).__name__


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _fmt(fmt, prefix):
    if not isinstance(fmt, str):
        raise _Err("bad format")
    if "@" in fmt:
        if prefix is None:
            raise _Err("byte order not resolved")
        fmt = fmt.replace("@", prefix)
    return fmt


def _read(data, offset, fmt):
    if not _is_int(offset) or offset < 0:
        raise _Err("bad offset")
    try:
        size = struct.calcsize(fmt)
        if offset + size > len(data):
            raise _Err("read past end of data")
        return struct.unpack_from(fmt, data, offset)
    except struct.error:
        raise _Err("bad struct format")


def _eval(expr, env):
    if _is_int(expr):
        return expr
    if isinstance(expr, str):
        if expr not in env:
            raise _Err("unknown name: " + expr)
        return env[expr]
    if isinstance(expr, dict) and len(expr) == 1:
        (op, args), = expr.items()
        if not isinstance(args, list):
            raise _Err("bad expression")
        vals = [_eval(a, env) for a in args]
        if op == "add":
            return sum(vals)
        if op == "mul":
            out = 1
            for v in vals:
                out *= v
            return out
        if op == "sub" and len(vals) == 2:
            return vals[0] - vals[1]
        if op == "ceil_div" and len(vals) == 2:
            if vals[1] == 0:
                raise _Err("division by zero")
            return -(-vals[0] // vals[1])
    raise _Err("bad expression")


def _read_array(data, arr, ent, typ, cnt, vfmt, voff, prefix, fields):
    """Read an array entry's values; append one fields tuple per value; return the values."""
    name = str(ent["name"])
    size = arr["type_sizes"].get(str(typ))
    if not _is_int(size) or size <= 0:
        raise _Err("unsupported array type for " + name)
    if not _is_int(cnt) or cnt < 1 or cnt > arr["max_count"]:
        raise _Err("array count out of range for " + name)
    if cnt * size <= arr["value_field_size"]:
        base = voff
    else:
        base = _read(data, voff, _fmt(arr["pointer_fmt"], prefix))[0]
    vals = []
    for i in range(cnt):
        off = base + i * size
        val = _read(data, off, vfmt)
        fields.append((name, off, vfmt, val))
        vals.append(val[0])
    return vals


def _trailer_match(data, tr, start):
    """Return the trailer start when its signature matches, else None. Only this check may skip."""
    try:
        pos = len(data) - tr["length"]
        sig = bytes.fromhex(tr["signature"])
        at = pos + tr["signature_offset"]
        if (pos >= start and pos >= 0 and at >= 0
                and data[at:at + len(sig)] == sig and len(sig) > 0):
            return pos
    except Exception:
        pass
    return None


def _read_declared(data, base, items, names, lo, hi, out):
    """Read each {"name", "at", "fmt"} at base + at; 0 is absent; nonzero must lie in [lo, hi)."""
    if not isinstance(items, list):
        raise _Err("malformed trailer declaration")
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("name"), str) or not _is_int(it.get("at")):
            raise _Err("malformed trailer declaration")
        v = _read(data, base + it["at"], _fmt(it.get("fmt"), None))[0]
        if not _is_int(v):
            raise _Err("malformed trailer declaration")
        names[it["name"]] = v
        if v != 0:
            if not (lo <= v < hi):
                raise _Err("declared offset out of range: " + it["name"])
            out.append(v)


def _trailer_end(data, tr, pos, start):
    """Data end for a matching trailer at `pos`, applying its declared offsets (Req 9.25)."""
    if "declared_offsets" not in tr and "area" not in tr:
        return pos
    ends = [pos]
    names = {}
    _read_declared(data, pos, tr.get("declared_offsets"), names, start, pos, ends)
    area = tr.get("area")
    if area is not None:
        if not isinstance(area, dict) or area.get("base") not in names:
            raise _Err("malformed trailer declaration")
        base = names[area["base"]]
        if base != 0:
            min_size = area.get("min_size")
            if not _is_int(min_size) or not _is_int(area.get("size_at")):
                raise _Err("malformed trailer declaration")
            size = _read(data, base + area["size_at"], _fmt(area.get("size_fmt"), None))[0]
            if not _is_int(size):
                raise _Err("malformed trailer declaration")
            if size < min_size or base + size > pos:
                raise _Err("declared area invalid")
            _read_declared(data, base, area.get("offsets"), {}, start, pos, ends)
    return min(ends)


def _parse(layout, data):
    if not isinstance(layout, dict):
        raise _Err("layout is not an object")
    if layout.get("schema") != "necropsy-layout/1":
        raise _Err("unsupported schema")
    if layout.get("kind") == "ambiguous":
        raise _Err("ambiguous layout: use parse_candidates")
    env = {}
    fields = []

    prefix = None
    bo = layout.get("byte_order")
    if bo is not None:
        raw = _read(data, bo["offset"], "%ds" % bo["length"])[0]
        prefix = bo["values"].get(raw.decode("latin-1"))
        if prefix is None:
            raise _Err("byte order marker not recognised")

    for f in layout.get("fields") or []:
        fmt = _fmt(f["fmt"], prefix)
        off = _eval(f["offset"], env)
        val = _read(data, off, fmt)
        if f.get("expect") is not None and val[0] != f["expect"]:
            raise _Err("expect failed for " + str(f["name"]))
        env[f["name"]] = val[0]
        fields.append((f["name"], off, fmt, val))

    tt = layout.get("tag_table")
    if tt is not None:
        at = _eval(tt["at"], env)
        cfmt = _fmt(tt["count_fmt"], prefix)
        n = _read(data, at, cfmt)[0]
        base = at + struct.calcsize(cfmt)
        esz = tt["entry_size"]
        if not _is_int(n) or n < 0 or n > _MAX_ENTRIES or not _is_int(esz) or esz <= 0:
            raise _Err("bad tag table")
        n = min(n, max(0, (len(data) - base) // esz))
        tags = {}
        for i in range(n):
            eo = base + i * esz
            t = _read(data, eo + tt["tag_offset"], _fmt(tt["tag_fmt"], prefix))[0]
            tags.setdefault(t, eo)
        for ent in tt.get("entries") or []:
            eo = tags.get(ent["tag"])
            if eo is None:
                if ent.get("optional") is True:
                    continue   # Req 9.26: an absent optional tag adds no value and no field
                if ent.get("default") is None:
                    raise _Err("tag missing: " + str(ent["name"]))
                env[ent["name"]] = ent["default"]
                continue
            typ = _read(data, eo + tt["type_offset"], _fmt(tt["type_fmt"], prefix))[0]
            cnt = _read(data, eo + tt["count_offset"], _fmt(tt["count_fmt_entry"], prefix))[0]
            vfmt = tt["value_fmt_by_type"].get(str(typ))
            if vfmt is None:
                raise _Err("unsupported tag type for " + str(ent["name"]))
            vfmt = _fmt(vfmt, prefix)
            voff = eo + tt["value_offset"]
            arr = ent.get("array")
            if arr is not None:
                vals = _read_array(data, arr, ent, typ, cnt, vfmt, voff, prefix, fields)
                if any(v != vals[0] for v in vals):
                    raise _Err("values not all equal for " + str(ent["name"]))
                value = vals[0]
            else:
                if tt.get("require_count") is not None and cnt != tt["require_count"]:
                    raise _Err("tag count mismatch for " + str(ent["name"]))
                val = _read(data, voff, vfmt)
                value = val[0]
                fields.append((ent["name"], voff, vfmt, val))
            if ent.get("expect") is not None and value != ent["expect"]:
                raise _Err("expect failed for " + str(ent["name"]))
            env[ent["name"]] = value

    img = layout["image"]
    width = _eval(img["width"], env)
    height = _eval(img["height"], env)
    depth = _eval(img["bit_depth"], env)
    align = img["row_alignment"]
    if align not in (1, 2, 4) or not _is_int(align):
        raise _Err("bad row_alignment")
    if width < 1 or height < 1 or depth < 1:
        raise _Err("non-positive image dimensions")

    d = layout["data"]
    start = _eval(d["start"], env)
    if d.get("end") is not None:
        end = _eval(d["end"], env)
    else:
        end = len(data)
        for tr in d.get("trailers") or []:
            pos = _trailer_match(data, tr, start)   # signature check only; may skip
            if pos is None:
                continue
            end = _trailer_end(data, tr, pos, start)   # an invalid declaration raises _Err
            break

    enc = d["encoding"]
    declared = enc
    if isinstance(enc, dict):
        declared = env.get(enc["field"])
        enc = enc["values"].get(str(declared), enc.get("otherwise"))
    if not isinstance(enc, str):
        raise _Err("encoding unresolved")
    if enc not in ("none", "rle_pcx", "rle_tga", "pnm_text", "packbits", "lzw_tiff",
                   "deflate_zlib", "lzma_xz"):
        raise _Err("unsupported encoding %s" % (declared,))

    if start < 0 or end < start or end > len(data):
        raise _Err("data region out of range")
    if img.get("row_bytes") is not None:
        stride = _eval(img["row_bytes"], env)    # Req 17.4: declared scanline bytes
        if stride < 1:
            raise _Err("non-positive row_bytes")
    else:
        raw_row = -(-(width * depth) // 8)
        stride = -(-raw_row // align) * align
    expected = stride * height
    if enc == "none":
        if end - start != expected:
            raise _Err("closure failed")
        pixels = bytes(data[start:end])
        maxval = img.get("maxval")
        if maxval is not None:   # Req 17.5: no sample may exceed the declared maximum
            if not _is_int(maxval):
                raise _Err("bad maxval")
            _check_samples(pixels, maxval, 2 if depth in (16, 48) else 1)
    elif enc == "pnm_text":
        maxval = img.get("maxval")
        if not _is_int(maxval) or maxval < 0 or maxval > 65535:
            raise _Err("bad maxval")
        pixels = _pnm_text(data, start, end, width, height, depth, maxval, expected)
    elif enc == "rle_tga":
        pixels = _rle_tga(data, start, end, expected, -(-depth // 8))
    elif enc == "packbits":
        pixels = _packbits(data, start, end, expected)
    elif enc == "lzw_tiff":
        pixels = _lzw_tiff(data, start, end, expected)
    elif enc == "deflate_zlib":
        pixels = _zlib_stream(data, start, end, expected)
    elif enc == "lzma_xz":
        pixels = _xz_stream(data, start, end, expected)
    else:
        pixels = _rle_pcx(data, start, end, expected)
    return {
        "ok": True, "width": width, "height": height, "bit_depth": depth,
        "row_alignment": align, "row_stride": stride, "encoding": enc, "data_start": start,
        "data_end": end, "pixels": pixels, "fields": fields,
    }


def _check_samples(pixels, maxval, size):
    """Error when a 1-byte or big-endian 2-byte sample is above maxval (Requirement 17.5)."""
    if size == 1:
        if maxval < 255 and pixels and max(pixels) > maxval:
            raise _Err("sample above the maximum value")
        return
    if maxval < 65535:
        for i in range(0, len(pixels) - 1, 2):
            if (pixels[i] << 8 | pixels[i + 1]) > maxval:
                raise _Err("sample above the maximum value")


_WS = frozenset(b" \t\n\x0b\x0c\r")


def _skip_ws(data, pos, end):
    """Skip whitespace and comments (`#` through the next 0x0A or 0x0D)."""
    while pos < end:
        b = data[pos]
        if b in _WS:
            pos += 1
        elif b == 0x23:
            while pos < end and data[pos] not in (0x0A, 0x0D):
                pos += 1
            pos += 1
        else:
            break
    return min(pos, end)


def _pnm_text(data, start, end, width, height, depth, maxval, expected):
    """Decode data[start:end] per the emitted pnm_text definition (Requirement 17.1).

    Output is built only from numbers read, so nothing is sized from the layout.
    """
    if depth not in (1, 8, 16, 24, 48):
        raise _Err("bad bit depth for pnm_text")
    total = width * height * (3 if depth in (24, 48) else 1)
    out = bytearray()
    pos = start
    count = 0
    bits = 0
    nbits = 0
    col = 0
    while count < total:
        pos = _skip_ws(data, pos, end)
        if pos >= end:
            raise _Err("data region ends before all numbers are read")
        if depth == 1:
            b = data[pos]
            if b not in (0x30, 0x31):
                raise _Err("above the maximum value" if 0x32 <= b <= 0x39 else "malformed number")
            pos += 1
            bits = (bits << 1) | (b - 0x30)
            nbits += 1
            col += 1
            if nbits == 8 or col == width:
                out.append((bits << (8 - nbits)) & 0xFF)
                bits = nbits = 0
                if col == width:
                    col = 0
        else:
            tok = pos
            while pos < end and data[pos] not in _WS and data[pos] != 0x23:
                pos += 1
            token = data[tok:pos]
            if not token.isdigit() or not token.isascii():
                raise _Err("malformed number")
            sig = token.lstrip(b"0")
            if len(sig) > 5 or (int(sig) if sig else 0) > maxval:
                raise _Err("number above the maximum value")
            value = int(sig) if sig else 0
            out.extend(value.to_bytes(2, "big") if maxval > 255 else bytes((value,)))
        if len(out) > expected:
            raise _Err("output exceeds the expected size")
        count += 1
    if _skip_ws(data, pos, end) < end:
        raise _Err("unread bytes remain")
    return bytes(out)


def _rle_pcx(data, start, end, expected):
    """Decode data[start:end] per the emitted rle_pcx definition (Requirement 9.28).

    Reads while fewer than `expected` bytes are produced and the region is not exhausted.
    Allocates at most `expected` bytes, checked before each write.
    """
    out = bytearray()
    pos = start
    while len(out) < expected and pos < end:
        b = data[pos]
        pos += 1
        if b >= 0xC0:
            if pos >= end:
                raise _Err("run marker is the last byte of the region")
            count = b & 0x3F
            if len(out) + count > expected:
                raise _Err("run exceeds the expected output")
            out.extend(data[pos:pos + 1] * count)
            pos += 1
        else:
            out.append(b)
    if len(out) < expected:
        raise _Err("output shorter than expected")
    if pos < end:
        raise _Err("unread bytes remain")
    return bytes(out)


def _rle_tga(data, start, end, expected, pixel_bytes):
    """Decode data[start:end] per the emitted rle_tga definition (Requirement 17.2).

    Packets form one stream; each packet is checked before it is written.
    """
    if pixel_bytes < 1:
        raise _Err("non-positive pixel_bytes")
    out = bytearray()
    pos = start
    while len(out) < expected and pos < end:
        h = data[pos]
        pos += 1
        if h >= 0x80:
            n, size = (h & 0x7F) + 1, pixel_bytes
        else:
            n, size = 1, (h + 1) * pixel_bytes
        if pos + pixel_bytes > end if h >= 0x80 else pos + size > end:
            raise _Err("region ends inside a packet")
        if len(out) + (n * pixel_bytes if h >= 0x80 else size) > expected:
            raise _Err("packet exceeds the expected output")
        if h >= 0x80:
            out.extend(data[pos:pos + pixel_bytes] * n)
            pos += pixel_bytes
        else:
            out.extend(data[pos:pos + size])
            pos += size
    if len(out) < expected:
        raise _Err("output shorter than expected")
    if pos < end:
        raise _Err("unread bytes remain")
    return bytes(out)


def _packbits(data, start, end, expected):
    """Decode data[start:end] per the emitted packbits definition (Requirement 17.1)."""
    out = bytearray()
    pos = start
    while len(out) < expected and pos < end:
        h = data[pos]
        pos += 1
        if h == 0x80:
            continue
        if h < 0x80:
            n = h + 1
            if pos + n > end:
                raise _Err("region ends inside a packet")
            if len(out) + n > expected:
                raise _Err("packet exceeds the expected output")
            out.extend(data[pos:pos + n])
            pos += n
        else:
            n = 257 - h
            if pos + 1 > end:
                raise _Err("region ends inside a packet")
            if len(out) + n > expected:
                raise _Err("packet exceeds the expected output")
            out.extend(data[pos:pos + 1] * n)
            pos += 1
    if len(out) < expected:
        raise _Err("output shorter than expected")
    if pos < end:
        raise _Err("unread bytes remain")
    return bytes(out)


def _lzw_tiff(data, start, end, expected):
    """Decode data[start:end] per the emitted lzw_tiff definition (Requirements 17.1, 12.8).

    Codes are read MSB first. Each entry is checked against `expected` before it is written;
    a table entry is at most 4094 bytes, so memory stays bounded.
    """
    total_bits = (end - start) * 8
    out = bytearray()
    table = [bytes((i,)) for i in range(256)] + [b"", b""]   # 258 entries; 256 CLEAR, 257 EOI
    width = 9
    prev = None
    bitpos = 0
    while True:
        if total_bits - bitpos < width:
            left = total_bits - bitpos
            if len(out) == expected and left < 8:
                return bytes(out)
            if len(out) == expected:
                raise _Err("a whole unread byte remains")
            raise _Err("region ends before the output is complete")
        code = 0
        for _ in range(width):
            byte = data[start + (bitpos >> 3)]
            code = (code << 1) | ((byte >> (7 - (bitpos & 7))) & 1)
            bitpos += 1
        if code == 257:
            if len(out) < expected:
                raise _Err("EOI before the output is complete")
            if start + (bitpos + 7) // 8 < end:
                raise _Err("a whole byte follows EOI")
            return bytes(out)
        if code == 256:
            del table[258:]
            width = 9
            prev = None
            continue
        if prev is None:
            if code >= 256:
                raise _Err("first code is not a literal")
            entry = table[code]
        elif code < len(table):
            entry = table[code]
        elif code == len(table):
            entry = prev + prev[:1]
        else:
            raise _Err("code above the table size")
        if len(out) + len(entry) > expected:
            raise _Err("entry exceeds the expected output")
        out.extend(entry)
        if prev is not None and len(table) < 4094:
            table.append(prev + entry[:1])
            if len(table) == 511:
                width = 10
            elif len(table) == 1023:
                width = 11
            elif len(table) == 2047:
                width = 12
        prev = entry


def _zlib_stream(data, start, end, expected):
    """Inflate data[start:end] as one zlib stream per the emitted deflate_zlib definition."""
    d = zlib.decompressobj()
    try:
        out = d.decompress(bytes(data[start:end]), expected + 1)
    except zlib.error:
        raise _Err("invalid zlib stream")
    if len(out) > expected:
        raise _Err("output exceeds the expected size")
    if not d.eof:
        raise _Err("zlib stream is not complete")
    if len(out) < expected:
        raise _Err("output shorter than expected")
    if d.unused_data:
        raise _Err("unread bytes remain")
    return bytes(out)


def _xz_stream(data, start, end, expected):
    """Decompress data[start:end] as one xz stream per the emitted lzma_xz definition."""
    d = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=67108864)
    try:
        out = d.decompress(bytes(data[start:end]), expected + 1)
    except lzma.LZMAError:
        raise _Err("invalid xz stream")
    if len(out) > expected:
        raise _Err("output exceeds the expected size")
    if not d.eof:
        raise _Err("xz stream is not complete")
    if len(out) < expected:
        raise _Err("output shorter than expected")
    if d.unused_data:
        raise _Err("unread bytes remain")
    return bytes(out)


def parse(layout, data):
    try:
        return _parse(layout, bytes(data))
    except _Err as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": "malformed layout: " + type(exc).__name__}


def parse_candidates(layout, data):
    try:
        if isinstance(layout, dict) and layout.get("kind") == "ambiguous":
            cands = layout.get("candidates")
            if not isinstance(cands, list):
                return [{"ok": False, "error": "no candidates"}]
            out = []
            for c in cands:
                if isinstance(c, dict) and "schema" not in c:
                    c = dict(c, schema=layout.get("schema"))
                out.append(parse(c, data))
            return out
        return [parse(layout, data)]
    except Exception as exc:
        return [{"ok": False, "error": "malformed layout: " + type(exc).__name__}]


_THIS_SOURCE = None


def make_parser_module(markdown):
    """Return self-contained Python source for a parser module embedding `markdown`."""
    global _THIS_SOURCE
    if _THIS_SOURCE is None:
        with open(__file__, encoding="utf-8") as fh:
            _THIS_SOURCE = fh.read()
    return (
        '"""Generated parser module (reference reader embedded)."""\n'
        "import json\nimport lzma\nimport re\nimport struct\nimport zlib\n\n"
        "MARKDOWN = " + repr(markdown) + "\n"
        "_READER_SOURCE = " + repr(_THIS_SOURCE) + "\n"
        "_NS = {'__name__': '_reference_reader', '__file__': __file__}\n"
        "exec(compile(_READER_SOURCE, '<reference_reader>', 'exec'), _NS)\n"
        "_LAYOUT = _NS['extract_layout'](MARKDOWN)\n\n\n"
        "def parse(data):\n"
        "    if isinstance(_LAYOUT, str):\n"
        "        return {'ok': False, 'error': _LAYOUT}\n"
        "    return _NS['parse'](_LAYOUT, data)\n\n\n"
        "def parse_candidates(data):\n"
        "    if isinstance(_LAYOUT, str):\n"
        "        return [{'ok': False, 'error': _LAYOUT}]\n"
        "    return _NS['parse_candidates'](_LAYOUT, data)\n"
    )
