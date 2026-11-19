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
)


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


def _trailers(origin: str) -> list:
    return [
        {"name": t.name, "length": t.length, "marker": t.marker}
        for t in TRAILER_REGISTRY
        if origin in t.applies_to
    ]


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


def _candidate_layout(cand, slug: str) -> dict:
    h = cand.hypothesis
    origin = h.probe_name
    path = h.revision_path
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
                               "9": "rle_tga", "10": "rle_tga", "11": "rle_tga"},
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
            "entries": [{"name": n, "tag": t, "default": d} for n, t, d in _TIFF_ENTRIES],
        }
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
            return _candidate_layout(cand, slug)
        if status == "UNRESOLVED_AMBIGUITY":
            probes = {c.hypothesis.probe_name for c in result.candidates}
            slug = _slug_for(probes, data)
            return {
                "schema": SCHEMA,
                "kind": "ambiguous",
                "slug": slug,
                "candidates": [_candidate_layout(c, slug) for c in result.candidates],
            }
        if status == "FAILED":
            return _error("nothing recovered: FAILED/" + str(getattr(result, "termination", "")))
        return _error("unsupported result type")
    except Exception as exc:
        return _error("layout error: " + type(exc).__name__)
