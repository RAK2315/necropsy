"""Turn an EngineResult into the JSON payload the frontend draws from (Requirement 2).

to_payload is a pure function of the result, the source bytes and the measured engine time.
It never raises.
"""
import base64
import json

from necropsy.emit import EmittedSpec, emit_spec

from web.pixels import PixelBuffer, decode

PIXEL_BUDGET = 500_000        # pixels converted per payload (Requirement 2.9)
SIZE_BUDGET = 4_000_000       # serialised bytes (Requirement 2.6)
NOT_RENDERED = "not rendered: payload limit"
PROBES = ("pcx", "tga", "pbm", "pnm", "tiff")


def stage_of(source: str) -> str:
    if source in PROBES:
        return "probe"
    if source.startswith("revision:"):
        return "revision"
    if source == "generic":
        return "generic"
    return "engine"


def palette_for(cand, data):
    """The 768 bytes after the 0x0C marker of a pcx_palette_256 trailer, or None."""
    if cand.trailer != "pcx_palette_256" or cand.hypothesis.bit_depth != 8 or cand.hypothesis.planes != 1:
        return None
    start = cand.data_end + 1                      # data_end is the marker's offset
    return data[start:start + 768] if start + 768 <= len(data) else None


def header_palette_for(cand, data):
    """The 48 bytes at 0x10 of a multi-plane PCX header (16 RGB entries), or None."""
    if cand.hypothesis.probe_name != "pcx" or cand.hypothesis.planes <= 1 or len(data) < 0x40:
        return None
    return bytes(data[0x10:0x40])


def _int_field(cand, name):
    """The integer value of the candidate's FieldRecord `name`, or None."""
    for f in cand.hypothesis.fields:
        if f.name == name:
            v = f.value
            if isinstance(v, tuple) and len(v) == 1 and isinstance(v[0], int) and not isinstance(v[0], bool):
                return v[0]
            return None
    return None


def color_map_for(cand):
    """The `color_map` value tuple (integers only) of the candidate's FieldRecord, or None (Requirement 2.5)."""
    for f in cand.hypothesis.fields:
        if f.name == "color_map":
            v = f.value
            if isinstance(v, tuple) and all(isinstance(x, int) and not isinstance(x, bool) for x in v):
                return v
            return None
    return None


def byte_order_for(cand):
    """b"II" or b"MM" from the TIFF `byte_order` field (bytes 0x00 to 0x01), else None."""
    for f in cand.hypothesis.fields:
        if f.name == "byte_order":
            v = f.value
            if isinstance(v, tuple) and len(v) == 1 and v[0] in (b"II", b"MM"):
                return bytes(v[0])
            return None
    return None


def channel_order_for(cand) -> str:
    """24/32-bit channel order from the format (Requirement 3.5): TGA B,G,R; TIFF R,G,B; generic B,G,R by convention."""
    probe = cand.hypothesis.probe_name
    if probe == "tiff":
        return "rgb"
    if probe == "generic":
        return "bgr-convention"
    return "bgr"


def photometric_for(cand):
    """0 or 1 when declared; "undeclared" for a TIFF grey candidate that declares none (Requirement 3.4)."""
    pi = _int_field(cand, "photometric_interpretation")
    if pi in (0, 1):
        return pi
    if pi is None and cand.hypothesis.probe_name == "tiff" and cand.hypothesis.bit_depth in (1, 4, 8, 12, 16):
        return "undeclared"
    return None


def _expand5(v: int) -> int:
    return (v * 255) // 31


def tga_colour_map_for(cand, data):
    """(palette, name, why_not) for an 8-bit TGA that declares a colour map (Requirement 3.16).

    palette is 768 bytes R,G,B indexed by pixel value, or None. The first entry index is the uint16 at 0x03,
    which the probe does not record, so it is read here and named in the note.
    """
    h = cand.hypothesis
    if h.probe_name != "tga" or h.bit_depth != 8 or _int_field(cand, "color_map_type") != 1:
        return None, None, None
    id_len = _int_field(cand, "id_length")
    length = _int_field(cand, "color_map_length")
    size = _int_field(cand, "color_map_entry_size")
    if None in (id_len, length, size) or len(data) < 5:
        return None, None, "colour map not applied: its fields were not read"
    first = data[3] | (data[4] << 8)
    per = {15: 2, 16: 2, 24: 3, 32: 4}.get(size)
    if per is None:
        return None, None, f"colour map not applied: {size}-bit entries are not supported"
    start = 18 + id_len
    if start + length * per > len(data):
        return None, None, "colour map not applied: it runs past the end of the file"
    used = h.width
    values = set()
    for r in range(h.height):
        values.update(cand.decoded[r * cand.row_stride: r * cand.row_stride + used])
    if values and (min(values) < first or max(values) >= first + length):
        return None, None, "colour map not applied: a pixel value falls outside the map"
    pal = bytearray(768)
    for k in range(length):
        i = first + k
        if i > 255:
            break
        o = start + k * per
        if per == 2:
            v = data[o] | (data[o + 1] << 8)
            rgb = (_expand5((v >> 10) & 31), _expand5((v >> 5) & 31), _expand5(v & 31))
        else:
            rgb = (data[o + 2], data[o + 1], data[o])          # stored B, G, R (, A)
        pal[3 * i:3 * i + 3] = bytes(rgb)
    return bytes(pal), f"colour map, {length} × {size}-bit entries, first index {first} (0x03)", None


def bottom_left_for(cand) -> bool:
    """True when the candidate's image_descriptor record declares a bottom-left origin."""
    for f in cand.hypothesis.fields:
        if f.name == "image_descriptor":
            v = f.value
            if isinstance(v, tuple) and len(v) == 1 and isinstance(v[0], int) and not isinstance(v[0], bool):
                return ((v[0] >> 5) & 1) == 0      # bit 5 clear: bottom-left
            return False
    return False


def _json_value(v):
    if isinstance(v, (bytes, bytearray)):
        return {"bytes": bytes(v).hex()}
    return v


def _field(f) -> dict:
    return {"name": f.name, "offset": f.offset, "fmt": f.fmt,
            "value": [_json_value(x) for x in f.value], "value_repr": repr(f.value)}


def _hypothesis(h) -> dict:
    d = {
        "width": h.width, "height": h.height, "bit_depth": h.bit_depth, "header_size": h.header_size,
        "row_alignment": h.row_alignment, "encoding": h.encoding, "declared_data_end": h.data_end,
        "probe_name": h.probe_name, "bounds": list(h.bounds) if h.bounds else None,
        "revision_path": list(h.revision_path), "fields": [_field(f) for f in h.fields],
    }
    if h.planes != 1:
        d["planes"] = h.planes
    if h.row_bytes is not None:
        d["row_bytes"] = h.row_bytes
    if h.ranges:
        d["ranges"] = [list(r) for r in h.ranges]
    if h.rows_per_strip is not None:
        d["rows_per_strip"] = h.rows_per_strip
    if h.tile is not None:
        d["tile"] = list(h.tile)
    if h.maxval is not None:
        d["maxval"] = h.maxval
    return d


def _candidate(c, data, budget: dict) -> dict:
    h = c.hypothesis
    pixels = h.width * h.height if h.width > 0 and h.height > 0 else 0
    if budget["spent"] + pixels > PIXEL_BUDGET:
        budget["spent"] = PIXEL_BUDGET + 1                      # nothing later is converted either
        render = {"failure": NOT_RENDERED}
    else:
        tga_pal, tga_name, tga_why = tga_colour_map_for(c, data)
        if tga_pal is not None:
            pal, name = tga_pal, tga_name
        else:
            pal, name = palette_for(c, data), "pcx_palette_256"
        out = decode(c.decoded, h.width, h.height, h.bit_depth, c.row_stride, h.probe_name,
                     pal, bottom_left_for(c), channel_order=channel_order_for(c), photometric=photometric_for(c),
                     palette_name=name, no_palette_why=tga_why, maxval=h.maxval,
                     planes=h.planes, header_palette=header_palette_for(c, data), byte_order=byte_order_for(c),
                     color_map=color_map_for(c),
                     bits_per_sample=_int_field(c, "bits_per_sample"),
                     samples_per_pixel=_int_field(c, "samples_per_pixel"),
                     photometric_interpretation=_int_field(c, "photometric_interpretation"),
                     image_type=_int_field(c, "image_type"),
                     image_descriptor=_int_field(c, "image_descriptor"))
        if isinstance(out, PixelBuffer):
            budget["spent"] += pixels
            render = {"width": out.width, "height": out.height, "channels": out.channels,
                      "data_b64": base64.b64encode(out.data).decode("ascii"), "note": out.note}
        else:
            render = {"failure": out.reason}
    d = _hypothesis(h)
    d.update({
        "row_stride": c.row_stride, "expected_decoded_bytes": c.expected_decoded_bytes,
        "data_start": c.data_start, "data_end": c.data_end, "trailer": c.trailer,
        "coherence_score": c.coherence_score, "coherence_status": c.coherence_status,
        "coherence_method": c.coherence_method,
        "alternative_paths": [list(p) for p in c.alternative_paths],
        "render": render,
    })
    return d


def _rejection(r) -> dict:
    return {"reason": r.reason, "source": r.source, "stage": stage_of(r.source),
            "discrepancy": r.discrepancy, "detail": r.detail,
            "hypothesis": _hypothesis(r.hypothesis) if r.hypothesis is not None else None}


def _size(obj) -> int:
    return len(json.dumps(obj, separators=(",", ":")))


def _spec(result, data) -> dict:
    spec = emit_spec(result, data)
    if isinstance(spec, EmittedSpec):
        return {"slug": spec.slug, "files": {n: t for n, t in spec.files}}
    return {"error": getattr(spec, "message", "nothing recovered")}


def _build(result, data, engine_ms) -> dict:
    budget = {"spent": 0}
    p = {"status": result.status, "total_checks": result.total_checks,
         "total_file_size": result.total_file_size, "engine_ms": round(engine_ms, 2)}
    if result.status == "RESOLVED":
        p["stage"] = result.stage
        cands = [result.candidate]
    elif result.status == "UNRESOLVED_AMBIGUITY":
        p["stage"] = result.stage
        p["reason"] = result.reason
        p["coherence_gap"] = result.coherence_gap
        cands = list(result.candidates)
    else:
        p["termination"] = result.termination
        cands = list(result.partial_candidates)
    key = "partial_candidates" if result.status == "FAILED" else "candidates"
    p[key] = [_candidate(c, data, budget) for c in cands]
    p["spec"] = _spec(result, data)

    # Size budget. Shrink the least important parts first: rejections (below), spec text, then pixel buffers.
    base = _size(p)
    if base > SIZE_BUDGET and "files" in p["spec"]:
        p["spec"] = {"slug": p["spec"]["slug"], "files": None, "too_large": True}
        base = _size(p)
    for cand in reversed(p[key]):
        if base <= SIZE_BUDGET:
            break
        if "data_b64" in cand["render"]:
            base -= len(cand["render"]["data_b64"])
            cand["render"] = {"failure": NOT_RENDERED}

    counts: dict = {}
    for r in result.rejections:
        by_reason = counts.setdefault(stage_of(r.source), {})
        by_reason[r.reason] = by_reason.get(r.reason, 0) + 1
    kept, used = [], base + 200
    for r in result.rejections:
        item = _rejection(r)
        used += _size(item) + 1
        if used > SIZE_BUDGET:
            break
        kept.append(item)
    p["rejections"] = kept
    p["rejections_omitted"] = len(result.rejections) - len(kept)
    p["rejection_counts"] = counts
    return p


def to_payload(result, data, engine_ms) -> dict:
    """The Result payload. Never raises; an internal failure becomes a FAILED payload."""
    try:
        return _build(result, bytes(data), float(engine_ms))
    except Exception as exc:
        return {"status": "FAILED", "termination": "internal_error", "total_checks": 0,
                "total_file_size": len(data) if isinstance(data, (bytes, bytearray)) else 0,
                "engine_ms": 0.0, "partial_candidates": [], "rejections": [
                    {"reason": "internal_error", "source": "engine", "stage": "engine", "discrepancy": None,
                     "detail": f"{type(exc).__name__}", "hypothesis": None}],
                "rejections_omitted": 0, "rejection_counts": {"engine": {"internal_error": 1}},
                "spec": {"error": "nothing recovered: FAILED/internal_error"}}