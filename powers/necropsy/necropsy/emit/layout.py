"""Layout builder: turns an engine result into a necropsy-layout/1 dict.

Pure and stdlib only. build_layout never raises. Failure contract: for a
FailureReport, an unknown result type or any internal error it returns
{"schema": "necropsy-layout/1", "kind": "error", "error": <str>}. Callers
(emit_spec) must check for kind == "error" before use.
"""

from __future__ import annotations

import hashlib

from necropsy.engine.trailers import TRAILER_REGISTRY

SCHEMA = "necropsy-layout/1"

_PCX_FIELDS = (
    ("manufacturer", 0x00, "B", 0x0A),
    ("encoding", 0x02, "B", None),
    ("bit_depth", 0x03, "B", None),
    ("xmin", 0x04, "<H", None),
    ("ymin", 0x06, "<H", None),
    ("xmax", 0x08, "<H", None),
    ("ymax", 0x0A, "<H", None),
    ("planes", 0x41, "B", None),
    ("bytes_per_line", 0x42, "<H", None),
)

_TGA_FIELDS = (
    ("id_length", 0x00, "B"),
    ("color_map_type", 0x01, "B"),
    ("image_type", 0x02, "B"),
    ("color_map_length", 0x05, "<H"),
    ("color_map_entry_size", 0x07, "B"),
    ("width", 0x0C, "<H"),
    ("height", 0x0E, "<H"),
    ("bit_depth", 0x10, "B"),
    ("image_descriptor", 0x11, "B"),
)

_TIFF_ENTRIES = (
    ("width", 256, None),
    ("height", 257, None),
    ("bits_per_sample", 258, None),
    ("compression", 259, 1),
    ("strip_offset", 273, None),
    ("samples_per_pixel", 277, 1),
    ("strip_byte_count", 279, None),
    ("planar_configuration", 284, 1),
)

_TIFF_BITS_ARRAY = {"max_count": 32, "value_field_size": 4, "pointer_fmt": "@I",
                    "type_sizes": {"3": 2, "4": 4}, "require": "all_equal"}


def _tiff_entry(name: str, tag: int, default) -> dict:
    # Only the tag-table entries named here carry an array rule or an expected value.
    return {"name": name, "tag": tag, "default": default,
            "expect": 1 if name == "planar_configuration" else None,
            "array": dict(_TIFF_BITS_ARRAY) if name == "bits_per_sample" else None}


def _error(message: str) -> dict:
    return {"schema": SCHEMA, "kind": "error", "error": message}


def _slug_for(probes: set, data: bytes) -> str:
    # One probe produced the result: its name. Generic Search, or probes that
    # disagree (ambiguous result across formats): unknown-<sha256[:8]>.
    if len(probes) == 1:
        name = next(iter(probes))
        if name != "generic":
            return name
    return "unknown-" + hashlib.sha256(data).hexdigest()[:8]


def _named(items) -> list:
    return [{"name": n, "at": at, "fmt": f} for n, at, f in items]


def _trailers(origin: str) -> list:
    out = []
    for t in TRAILER_REGISTRY:
        if origin not in t.applies_to:
            continue
        d = {"name": t.name, "length": t.length, "signature": t.signature.hex(),
             "signature_offset": t.signature_offset}
        # Requirement 9.23: both keys are omitted when the entry declares nothing.
        if t.declared_offsets:
            d["declared_offsets"] = _named(t.declared_offsets)
        a = t.declared_area
        if a is not None:
            d["area"] = {"base": a.base, "size_at": a.size_at, "size_fmt": a.size_fmt,
                         "min_size": a.min_size, "offsets": _named(a.offsets)}
        out.append(d)
    return out


def _fixed_fields(spec) -> list:
    return [{"name": n, "offset": o, "fmt": f, "expect": e} for n, o, f, e in spec]


def _base(kind: str, slug: str) -> dict:
    return {
        "schema": SCHEMA,
        "kind": kind,
        "slug": slug,
        "byte_order": None,
        "fields": [],
        "tag_table": None,
        "image": {},
        "data": {},
        "equivalent_reads": {},
        "observed": {},
    }


def _observed(cand) -> dict:
    h = cand.hypothesis
    return {
        "width": h.width,
        "height": h.height,
        "bit_depth": h.bit_depth,
        "row_alignment": h.row_alignment,
        "data_start": cand.data_start,
        "data_end": cand.data_end,
    }


_BROKE_RULES = ("probe_precondition_failed", "field_out_of_bounds")
_BROKE_RULES_NOTE = ("This layout describes this one file only, not the format, because the file "
                     "broke the format's own rules.")


def _broke_rules(origin: str, rejections) -> bool:
    return origin in ("pcx", "tga", "pbm", "tiff") and any(
        r.source == origin and r.reason in _BROKE_RULES for r in rejections)


OVERRIDING_STRATEGIES = frozenset({"rle_pcx"})
_OVERRIDE_NOTE = ("This layout describes this one file only, not the format, because revision "
                  "overrode the file's own encoding declaration: the declaration was overridden "
                  "because only the revised reading closes.")


def _overrides(path) -> bool:
    return bool(OVERRIDING_STRATEGIES.intersection(path))


def _rule_breaking_layout(cand, slug: str, note: str = _BROKE_RULES_NOTE) -> dict:
    # Requirement 9.20: this file's literal values; fields read with expect null.
    h = cand.hypothesis
    out = _base("file", slug)
    first = {}
    for f in h.fields:
        first.setdefault(f.name, f)
    out["fields"] = [{"name": n, "offset": f.offset, "fmt": f.fmt, "expect": None}
                     for n, f in first.items()]
    out["image"] = {"width": h.width, "height": h.height, "bit_depth": h.bit_depth,
                    "row_alignment": h.row_alignment}
    out["data"] = {"start": cand.data_start, "end": cand.data_end, "encoding": h.encoding,
                   "trailers": _trailers(h.probe_name)}
    out["note"] = note
    out["observed"] = _observed(cand)
    return out


def _candidate_layout(cand, slug: str, rejections=(), data_len=None) -> dict:
    h = cand.hypothesis
    origin = h.probe_name
    path = h.revision_path
    if _broke_rules(origin, rejections):
        return _rule_breaking_layout(cand, slug)
    if _overrides(path):
        return _rule_breaking_layout(cand, slug, _OVERRIDE_NOTE)
    if origin == "pcx":
        out = _base("format", slug)
        out["fields"] = _fixed_fields(_PCX_FIELDS)
        if "inclusive_bounds" in path:
            width = {"add": [{"sub": ["xmax", "xmin"]}, 1]}
            height = {"add": [{"sub": ["ymax", "ymin"]}, 1]}
        else:
            width, height = "xmax", "ymax"
        if "rle_pcx" in path:
            encoding = "rle_pcx"
        else:
            encoding = {"field": "encoding", "values": {"0": "none", "1": "rle_pcx"}}
        out["image"] = {"width": width, "height": height, "bit_depth": "bit_depth",
                        "row_alignment": h.row_alignment}
        if h.planes > 1 and h.row_bytes is not None:
            # Requirement 17.4: the scanline is `planes` planes of bytes_per_line bytes.
            out["image"]["bit_depth"] = {"mul": ["bit_depth", "planes"]}
            out["image"]["row_bytes"] = {"mul": ["planes", "bytes_per_line"]}
        out["data"] = {"start": 128, "end": None, "encoding": encoding,
                       "trailers": _trailers("pcx")}
    elif origin == "tga":
        out = _base("format", slug)
        out["fields"] = [{"name": n, "offset": o, "fmt": f, "expect": None}
                         for n, o, f in _TGA_FIELDS]
        start = {"add": [18, "id_length",
                         {"mul": ["color_map_type", "color_map_length",
                                  {"ceil_div": ["color_map_entry_size", 8]}]}]}
        encoding = {"field": "image_type",
                    "values": {"1": "none", "2": "none", "3": "none",
                               "9": "unsupported", "10": "unsupported",
                               "11": "unsupported"},
                    "otherwise": "unsupported"}
        out["image"] = {"width": "width", "height": "height", "bit_depth": "bit_depth",
                        "row_alignment": h.row_alignment}
        out["data"] = {"start": start, "end": None, "encoding": encoding,
                       "trailers": _trailers("tga")}
    elif origin == "tiff":
        out = _base("format", slug)
        out["byte_order"] = {"offset": 0, "length": 2, "values": {"II": "<", "MM": ">"}}
        out["fields"] = [
            {"name": "magic", "offset": 2, "fmt": "@H", "expect": 42},
            {"name": "ifd_offset", "offset": 4, "fmt": "@I", "expect": None},
        ]
        out["tag_table"] = {
            "at": "ifd_offset", "count_fmt": "@H", "entry_size": 12,
            "tag_offset": 0, "tag_fmt": "@H", "type_offset": 2, "type_fmt": "@H",
            "count_offset": 4, "count_fmt_entry": "@I", "value_offset": 8,
            "value_fmt_by_type": {"3": "@H", "4": "@I"}, "require_count": 1,
            "entries": [_tiff_entry(n, t, d) for n, t, d in _TIFF_ENTRIES],
        }
        # Requirement 9.26: appended only when the candidate read tag 262.
        if any(f.name == "photometric_interpretation" for f in h.fields):
            out["tag_table"]["entries"].append(
                {"name": "photometric_interpretation", "tag": 262, "default": None,
                 "expect": None, "array": None, "optional": True})
        out["image"] = {"width": "width", "height": "height",
                        "bit_depth": {"mul": ["bits_per_sample", "samples_per_pixel"]},
                        "row_alignment": h.row_alignment}
        out["data"] = {
            "start": "strip_offset",
            "end": {"add": ["strip_offset", "strip_byte_count"]},
            "encoding": {"field": "compression", "values": {"1": "none"},
                         "otherwise": "unsupported"},
            "trailers": [],
        }
    elif origin == "pbm":
        # Width and height are ASCII tokens, which the schema cannot evaluate,
        # so the image values are this file's literals; the token reads are
        # listed as fields for documentation.
        out = _base("file", slug)
        out["fields"] = [
            {"name": f.name, "offset": f.offset, "fmt": f.fmt, "expect": None}
            for f in h.fields
        ]
        out["image"] = {"width": h.width, "height": h.height, "bit_depth": h.bit_depth,
                        "row_alignment": h.row_alignment}
        out["data"] = {"start": h.header_size, "end": None, "encoding": "none",
                       "trailers": _trailers("pbm")}
    else:
        out = _base("file", slug)
        first = {}
        reads = {}
        for f in h.fields:
            first.setdefault(f.name, f)
            reads.setdefault(f.name, []).append([f.fmt, f.offset])
        out["fields"] = [
            {"name": n, "offset": f.offset, "fmt": f.fmt, "expect": None}
            for n, f in first.items()
        ]
        out["image"] = {"width": "width", "height": "height", "bit_depth": "bit_depth",
                        "row_alignment": h.row_alignment}
        out["data"] = {"start": h.header_size, "end": None, "encoding": h.encoding,
                       "trailers": _trailers("generic")}
        out["equivalent_reads"] = reads
    # Requirement 9.27: an end-of-file reading (data_end = len(data)) of a pcx, tga or
    # generic candidate strips no trailer, so the reference reader runs to the file end.
    if origin in ("pcx", "tga", "generic") and data_len is not None and cand.hypothesis.data_end == data_len:
        out["data"]["end"] = None
        out["data"]["trailers"] = []
    out["observed"] = _observed(cand)
    return out


def build_layout(result, data) -> dict:
    """Build a necropsy-layout/1 dict. Never raises; see module docstring."""
    try:
        data = bytes(data)
        status = getattr(result, "status", None)
        if status == "RESOLVED":
            cand = result.candidate
            slug = _slug_for({cand.hypothesis.probe_name}, data)
            return _candidate_layout(cand, slug, getattr(result, "rejections", ()), len(data))
        if status == "UNRESOLVED_AMBIGUITY":
            probes = {c.hypothesis.probe_name for c in result.candidates}
            slug = _slug_for(probes, data)
            return {
                "schema": SCHEMA,
                "kind": "ambiguous",
                "slug": slug,
                "candidates": [_candidate_layout(c, slug, getattr(result, "rejections", ()), len(data)) for c in result.candidates],
            }
        if status == "FAILED":
            return _error("nothing recovered: FAILED/" + str(getattr(result, "termination", "")))
        return _error("unsupported result type")
    except Exception as exc:
        return _error("layout error: " + type(exc).__name__)
