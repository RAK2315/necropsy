"""Reference reader: a generic interpreter of necropsy-layout/1.

Contains no knowledge of any specific format. Imports only json, re, struct.
Never raises on arbitrary bytes or malformed layouts.
"""
import json
import re
import struct

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
            try:
                pos = len(data) - tr["length"]
                sig = bytes.fromhex(tr["signature"])
                at = pos + tr["signature_offset"]
                if (pos >= start and pos >= 0 and at >= 0
                        and data[at:at + len(sig)] == sig and len(sig) > 0):
                    end = pos
                    break
            except Exception:
                continue

    enc = d["encoding"]
    if isinstance(enc, dict):
        key = str(env[enc["field"]]) if enc["field"] in env else None
        enc = enc["values"].get(key, enc.get("otherwise"))
    if not isinstance(enc, str):
        raise _Err("encoding unresolved")
    if enc != "none":
        raise _Err("encoding not supported by reference reader")

    if start < 0 or end < start or end > len(data):
        raise _Err("data region out of range")
    raw_row = -(-(width * depth) // 8)
    stride = -(-raw_row // align) * align
    if end - start != stride * height:
        raise _Err("closure failed")
    return {
        "ok": True, "width": width, "height": height, "bit_depth": depth,
        "row_alignment": align, "encoding": enc, "data_start": start,
        "data_end": end, "pixels": bytes(data[start:end]), "fields": fields,
    }


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
        "import json\nimport re\nimport struct\n\n"
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
