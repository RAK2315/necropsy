"""Spec renderers for the emitter.

Pure and stdlib only. render_requirements never raises: on any failure, or when
the layout is an error layout, it returns a minimal valid requirements document
that states the error. The document holds exactly one ``necropsy-layout`` block
(in the Introduction) except in that error case, where it holds none.
"""

from __future__ import annotations

import json
import struct

_BYTE_ORDER_TEXT = "declared by bytes 0x00\u20130x01 (II little-endian, MM big-endian)"


# ---------------------------------------------------------------- helpers


def _hex(value) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return "0x%04X" % value
    return _ex(value)


def _ex(e) -> str:
    """Render a layout expression as prose."""
    if isinstance(e, bool):
        return str(e)
    if isinstance(e, int):
        return str(e)
    if isinstance(e, str):
        return "`%s`" % e
    if isinstance(e, dict) and len(e) == 1:
        (op, args), = e.items()
        parts = [_ex(a) for a in args]
        if op == "add":
            return "(" + " + ".join(parts) + ")"
        if op == "sub":
            return "(" + " - ".join(parts) + ")"
        if op == "mul":
            return "(" + " \u00d7 ".join(parts) + ")"
        if op == "ceil_div":
            return "ceil(" + " / ".join(parts) + ")"
    return str(e)


def _size(fmt: str):
    try:
        return struct.calcsize("<" + fmt.lstrip("@<>=!"))
    except struct.error:
        return None


def _describe_fmt(fmt: str) -> str:
    size = _size(fmt)
    n = "%s byte%s" % (size, "" if size == 1 else "s") if size is not None else "unknown size"
    if fmt.startswith("@"):
        return "%s, %s" % (_BYTE_ORDER_TEXT, n)
    if fmt.startswith("<"):
        return "little-endian, %s" % n
    if fmt.startswith(">"):
        return "big-endian, %s" % n
    if fmt.endswith("s"):
        return "raw ASCII bytes, no byte order, %s" % n
    return "single value, no byte order, %s" % n


def _encoding_text(enc) -> str:
    if isinstance(enc, str):
        return "`%s`" % enc
    if isinstance(enc, dict):
        pairs = ", ".join("%s \u2192 `%s`" % (k, v) for k, v in enc.get("values", {}).items())
        text = "selected by the value of `%s` (%s)" % (enc.get("field"), pairs)
        if "otherwise" in enc:
            text += ", otherwise `%s`" % enc["otherwise"]
        return text
    return str(enc)


def _plural(n: int, word: str) -> str:
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


# ------------------------------------------------- per-layout criteria


def _signature(lay: dict, origin: str) -> list:
    out = []
    bo = lay.get("byte_order")
    if bo:
        off, ln = bo.get("offset", 0), bo.get("length", 2)
        vals = "; ".join("`%s` selects `%s`" % (k, v) for k, v in bo.get("values", {}).items())
        out.append(
            "THE parser SHALL read the byte-order marker, %s at offset %s, and resolve `@` in "
            "every struct format to the prefix it selects (%s)."
            % (_plural(ln, "byte"), _hex(off), vals)
        )
        out.append(
            "IF the byte-order marker is not one of the listed values, "
            "THEN THE parser SHALL return an error."
        )
    if origin == "pbm":
        out.append(
            "THE parser SHALL require bytes 0x0000\u20130x0002 to equal `P4\\n` "
            "(the characters P and 4 followed by a line feed, 0x0A)."
        )
        out.append("IF the signature differs, THEN THE parser SHALL return an error.")
        out.append(
            "THE parser SHALL parse the text header only within the first 1,024 bytes of the file."
        )
        out.append(
            "THE parser SHALL skip every line that begins with `#` as a comment, starting "
            "immediately after the signature."
        )
        out.append(
            "THE parser SHALL read the next line as exactly two ASCII decimal tokens separated "
            "by whitespace: width, then height."
        )
        out.append(
            "THE parser SHALL end the header after the newline that closes the dimensions line, "
            "so that the data region starts at the offset of the following byte."
        )
    for f in lay.get("fields") or []:
        if f.get("expect") is not None:
            e = f["expect"]
            out.append(
                "THE parser SHALL require `%s` at offset %s to equal %d (0x%02X), read using "
                "struct format `%s` (%s)."
                % (f["name"], _hex(f["offset"]), e, e, f["fmt"], _describe_fmt(f["fmt"]))
            )
    if not out:
        out.append("THE parser SHALL NOT require any fixed signature bytes: this layout declares none.")
    if origin == "generic":
        out.append(
            "THE parser SHALL treat this layout as describing this one file's layout only. "
            "It does not describe a format, and no other file is implied to follow it."
        )
    return out


def _fields(lay: dict) -> list:
    out = []
    reads = lay.get("equivalent_reads") or {}
    for f in lay.get("fields") or []:
        text = "THE parser SHALL read `%s` at offset %s using struct format `%s` (%s)." % (
            f["name"], _hex(f["offset"]), f["fmt"], _describe_fmt(f["fmt"]))
        alts = reads.get(f["name"]) or []
        if len(alts) > 1:
            text = text[:-1] + ". The same bytes admit equivalent reads: %s." % "; ".join(
                "`%s` at %s" % (fmt, _hex(off)) for fmt, off in alts)
        out.append(text)
    tt = lay.get("tag_table")
    if tt:
        out.append(
            "THE parser SHALL walk the tag table located at the offset held in %s: read a "
            "count using struct format `%s` (%s), then that many entries of %d bytes each "
            "(capped by the bytes available), and use the first entry for each tag."
            % (_ex(tt["at"]), tt["count_fmt"], _describe_fmt(tt["count_fmt"]), tt["entry_size"])
        )
        vf = ", ".join("type %s uses `%s` (%s)" % (k, v, _describe_fmt(v))
                       for k, v in tt.get("value_fmt_by_type", {}).items())
        out.append(
            "THE parser SHALL read, within each entry, the tag using `%s` at entry offset %s "
            "(%s), the type using `%s` at entry offset %s (%s), and the count using `%s` at "
            "entry offset %s (%s)."
            % (tt["tag_fmt"], _hex(tt["tag_offset"]), _describe_fmt(tt["tag_fmt"]),
               tt["type_fmt"], _hex(tt["type_offset"]), _describe_fmt(tt["type_fmt"]),
               tt["count_fmt_entry"], _hex(tt["count_offset"]),
               _describe_fmt(tt["count_fmt_entry"]))
        )
        out.append(
            "THE parser SHALL read each tag value at entry offset %s using the struct format "
            "chosen by the entry type: %s." % (_hex(tt["value_offset"]), vf)
        )
        out.append(
            "IF a tag entry has a count other than %s or a type not listed, "
            "THEN THE parser SHALL return an error." % tt.get("require_count")
        )
        for ent in tt.get("entries") or []:
            default = ent.get("default")
            rule = ("WHERE the tag is absent, the value SHALL be %d" % default
                    if default is not None else "IF the tag is absent, THEN THE parser SHALL return an error")
            out.append(
                "THE parser SHALL read tag entry `%s` from the entry whose tag equals %d, at "
                "value offset %s of that entry. %s."
                % (ent["name"], ent["tag"], _hex(tt["value_offset"]), rule)
            )
    if not out:
        out.append("THE parser SHALL read no header fields: this layout declares none.")
    return out


def _data(lay: dict, cand, origin: str) -> list:
    out = []
    d = lay.get("data") or {}
    img = lay.get("image") or {}
    path = list(cand.hypothesis.revision_path) if cand is not None else []
    out.append(
        "THE parser SHALL take the image width as %s, the height as %s and the bit depth as %s "
        "bits per pixel, with rows padded to a multiple of %s byte%s."
        % (_ex(img.get("width")), _ex(img.get("height")), _ex(img.get("bit_depth")),
           img.get("row_alignment"), "" if img.get("row_alignment") == 1 else "s")
    )
    if origin == "pbm":
        out.append(
            "THE parser SHALL start the data region at the offset after the header's closing "
            "newline, which is %s in the source file." % _ex(d.get("start"))
        )
    else:
        out.append("THE parser SHALL start the data region at %s." % _ex(d.get("start")))
    if d.get("end") is not None:
        out.append("THE parser SHALL end the data region at %s." % _ex(d["end"]))
    else:
        out.append("THE parser SHALL end the data region at the end of the file, unless a trailer applies.")
    trailers = d.get("trailers") or []
    for t in trailers:
        out.append(
            "WHEN the byte at offset (file length - %d) is at or after the data start and equals "
            "0x%02X, THE parser SHALL treat the trailing %s as trailer `%s` and end the data "
            "region at that position."
            % (t["length"], t["marker"], _plural(t["length"], "byte"), t["name"])
        )
    if not trailers:
        out.append("THE parser SHALL NOT strip any trailer from the data region.")
    out.append("THE parser SHALL decode the data region using encoding %s." % _encoding_text(d.get("encoding")))
    if "rle_pcx" in path:
        out.append(
            "WHEN the file's own encoding declaration says the data is uncompressed, THE parser "
            "SHALL ignore it: the encoding declaration was overridden by revision, which found "
            "that only `rle_pcx` decoding closes."
        )
    if "inclusive_bounds" in path:
        out.append(
            "THE parser SHALL read the bounds as inclusive, so that width = xmax - xmin + 1 and "
            "height = ymax - ymin + 1, as found by the `inclusive_bounds` revision."
        )
    if path:
        out.append(
            "WHEN parsing the source file, THE parser SHALL find that it closes only through the revision path %s."
            % ", ".join("`%s`" % p for p in path)
        )
    return out


def _closure(lay: dict, cand) -> list:
    out = []
    obs = lay.get("observed") or {}
    enc = (lay.get("data") or {}).get("encoding")
    out.append(
        "THE parser SHALL accept the data region only when its decoded size equals "
        "`row_stride` \u00d7 `height` bytes, where row_stride = "
        "ceil(ceil(width \u00d7 bit_depth / 8) / row_alignment) \u00d7 row_alignment."
    )
    if enc == "none" or isinstance(enc, dict):
        out.append(
            "WHEN the encoding is `none`, THE parser SHALL require data_end - data_start to "
            "equal row_stride \u00d7 height."
        )
    if (isinstance(enc, str) and enc != "none") or isinstance(enc, dict):
        out.append(
            "WHEN the encoding is a run-length encoding, THE parser SHALL require the decoder "
            "to consume the whole data region and produce exactly row_stride \u00d7 height bytes."
        )
    try:
        w, h, b, a = obs["width"], obs["height"], obs["bit_depth"], obs["row_alignment"]
        start, end = obs["data_start"], obs["data_end"]
        raw = -(-(w * b) // 8)
        stride = -(-raw // a) * a
        expected = cand.expected_decoded_bytes if cand is not None else stride * h
        out.append(
            "WHEN parsing the source file, THE parser SHALL find row_stride = ceil(ceil(%d \u00d7 %d / 8) / %d) "
            "\u00d7 %d = %d bytes, an expected size of %d \u00d7 %d = %d bytes, and a data region "
            "[%d, %d) of %d bytes, so that closure holds."
            % (w, b, a, a, stride, stride, h, stride * h, start, end, end - start)
        )
        if expected != stride * h:
            out[-1] = out[-1][:-1] + " (decoder output: %d bytes)." % expected
    except Exception:
        out.append("WHEN parsing the source file, THE parser SHALL satisfy the closure rule.")
    return out


def _observed(lay: dict) -> list:
    return [
        "WHEN parsing the source file, THE parser SHALL return %s = %s." % (k, v)
        for k, v in (lay.get("observed") or {}).items()
    ]


# ------------------------------------------------------------- documents


def _criteria(items: list, prefix: str = "") -> str:
    return "\n".join("%d. %s%s" % (i, prefix, t) for i, t in enumerate(items, 1))


def _requirement(n: int, title: str, story: str, items: list, prefix: str = "") -> str:
    return "### Requirement %d: %s\n\n**User Story:** %s\n\n#### Acceptance Criteria\n\n%s\n" % (
        n, title, story, _criteria(items, prefix))


_GLOSSARY = (
    "- **Parser**: A parser that reads the layout described in this document.\n"
    "- **Source file**: The file NECROPSY analysed to produce this document.\n"
    "- **Layout block**: The fenced `necropsy-layout` JSON block in the Introduction. "
    "It states the same rules in machine-readable form.\n"
    "- **Closure**: The check that the data region decodes to exactly `row_stride` \u00d7 `height` bytes.\n"
    "- **Struct format**: A Python `struct` format string with an explicit byte-order prefix, "
    "or `@` where the prefix is declared by the file."
)


def _document(intro: str, glossary: str, body: str) -> str:
    return (
        "# Requirements Document\n\n## Introduction\n\n%s\n\n## Glossary\n\n%s\n\n"
        "## Requirements\n\n%s" % (intro, glossary, body)
    )


def _error_document(message: str) -> str:
    message = " ".join(str(message).split())
    intro = "NECROPSY could not describe this input. Error: %s." % message.rstrip(".")
    story = ("As a NECROPSY user, I want to be told when no spec could be produced, "
             "so that I do not rely on an empty result.")
    req = _requirement(1, "Error report", story, [
        "THE system SHALL report that no layout was recovered: %s." % message.rstrip(".")])
    return _document(intro, _GLOSSARY, req)


def _origin(lay: dict, cand) -> str:
    if cand is not None:
        return cand.hypothesis.probe_name
    return "generic" if lay.get("kind") == "file" else lay.get("slug", "")


def _render(layout: dict, result) -> str:
    kind = layout.get("kind")
    if kind == "error":
        return _error_document(layout.get("error", "unknown error"))
    block = "```necropsy-layout\n%s\n```" % json.dumps(layout, indent=2)

    if kind == "ambiguous":
        lays = layout.get("candidates") or []
        cands = list(getattr(result, "candidates", ()) or ())
        pairs = [(lay, cands[i] if i < len(cands) else None) for i, lay in enumerate(lays)]
        intro = (
            "This document describes %d candidate layouts of one source file. Each candidate "
            "passes the closure check, the bytes cannot separate them, and this document "
            "asserts no single candidate. The slug is `%s`.\n\n"
            "The machine-readable layout is:\n\n%s"
            % (len(pairs), layout.get("slug"), block)
        )
        body = []
        for k, (lay, cand) in enumerate(pairs, 1):
            origin = _origin(lay, cand)
            items = (_signature(lay, origin) + _fields(lay) + _data(lay, cand, origin)
                     + _closure(lay, cand) + _observed(lay))
            obs = lay.get("observed") or {}
            title = "Candidate %d reading: %s \u00d7 %s at %s bits per pixel, data starting at byte %s" % (
                k, obs.get("width"), obs.get("height"), obs.get("bit_depth"), obs.get("data_start"))
            body.append(_requirement(
                k, title,
                "As a developer, I want candidate %d stated in full, so that I can build a parser "
                "for it if it is the reading I need." % k,
                items, "WHERE candidate %d is assumed, " % k))
        n = len(pairs)
        sep = [
            "THE parser SHALL treat each of the %d candidates as having passed the closure check "
            "on the source file." % n,
            "THE parser SHALL NOT select a single candidate: the bytes of the source file cannot "
            "separate the candidates, and every candidate is a valid reading of them.",
            "WHEN row coherence is reported for a candidate, THE parser SHALL treat it as a "
            "heuristic (`row_mad_ratio`), not as evidence that the candidate is correct.",
            "THE heuristic SHALL be known to fail when narrower strides score better on smooth images.",
            "THE heuristic SHALL be known to fail when identical bytes at an identical stride, "
            "split into different bit depths, score identically.",
            "THE heuristic SHALL be known to fail when a header can absorb whole rows.",
            "WHEN a consumer needs one layout, THE parser SHALL require the consumer to choose "
            "from outside the bytes, and SHALL return every candidate until it does.",
        ]
        body.append(_requirement(
            n + 1, "Candidates cannot be separated by the bytes",
            "As a user, I want it stated that the candidates are indistinguishable from the "
            "bytes, so that I do not mistake a heuristic for a decision.", sep))
        return _document(intro, _GLOSSARY, "\n".join(body))

    if kind not in ("format", "file"):
        return _error_document("unsupported layout kind")
    cand = getattr(result, "candidate", None)
    origin = _origin(layout, cand)
    if kind == "file" and origin == "generic":
        scope = (" This is the layout of this one file only. It is not a format, and no other "
                 "file is implied to follow it.")
    elif kind == "format":
        scope = " It states the rules of the format together with the values observed in the source file."
    else:
        scope = " The text-header rules are stated in prose because the layout schema cannot express them."
    intro = (
        "This document describes the layout of one source file as recovered by NECROPSY "
        "(slug `%s`, layout kind `%s`).%s\n\nThe machine-readable layout is:\n\n%s"
        % (layout.get("slug"), kind, scope, block)
    )
    story = "As a developer, I want the %s stated precisely, so that I can build a parser from this document alone."
    reqs = [
        _requirement(1, "Signature and byte order", story % "signature and byte order",
                     _signature(layout, origin)),
        _requirement(2, "Fields", story % "fields", _fields(layout)),
        _requirement(3, "Data region and encoding", story % "data region and encoding",
                     _data(layout, cand, origin)),
        _requirement(4, "Closure", story % "closure rule", _closure(layout, cand)),
        _requirement(5, "Observed values", "As a developer, I want the values observed in the "
                     "source file, so that I can check my parser against it.", _observed(layout)),
    ]
    return _document(intro, _GLOSSARY, "\n".join(reqs))


def render_requirements(layout, result, data) -> str:
    """Render the emitted requirements.md. Never raises."""
    try:
        return _render(layout, result)
    except Exception as exc:
        try:
            return _error_document("render error: " + type(exc).__name__)
        except Exception:
            return ("# Requirements Document\n\n## Introduction\n\nRender error.\n\n## Glossary\n\n"
                    "- **Error**: A render failure.\n\n## Requirements\n\n### Requirement 1: Error\n\n"
                    "**User Story:** As a user, I want the error stated.\n\n#### Acceptance Criteria\n\n"
                    "1. THE system SHALL report a render error.\n")


# ------------------------------------------------------- design document

_MAX_REJECTIONS = 500
_COHERENCE_LABEL = "heuristic (row_mad_ratio)"


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: tuple, rows: list) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(lines)


def _path_text(path) -> str:
    return "[" + ", ".join(str(p) for p in path) + "]"


def _closure_line(cand) -> str:
    h = cand.hypothesis
    start, end = cand.data_start, cand.data_end
    if h.encoding == "none":
        return "closure: [%d, %d) holds %d bytes = %d x %d" % (
            start, end, end - start, cand.row_stride, h.height)
    return "closure: %s decoded [%d, %d) to %d bytes = %d x %d, all input consumed" % (
        h.encoding, start, end, cand.expected_decoded_bytes, cand.row_stride, h.height)


def _coherence_line(cand) -> str:
    if cand.coherence_status == "scored" and cand.coherence_score is not None:
        return "coherence: %s = %.4f" % (_COHERENCE_LABEL, cand.coherence_score)
    return "coherence: %s %s" % (_COHERENCE_LABEL, cand.coherence_status)


def _structure_table(cand) -> str:
    h = cand.hypothesis
    dims = _table(("property", "value"), [
        ("width", h.width), ("height", h.height), ("bit_depth", h.bit_depth),
        ("header_size", h.header_size), ("row_alignment", h.row_alignment),
        ("encoding", h.encoding), ("row_stride", cand.row_stride),
        ("expected_decoded_bytes", cand.expected_decoded_bytes),
    ])
    if not h.fields:
        return dims
    fields = _table(("offset", "field", "struct format", "value"), [
        ("0x%04X" % f.offset, f.name, f.fmt, ", ".join(str(v) for v in f.value))
        for f in h.fields
    ])
    return dims + "\n\n" + fields


def _candidate_block(cand, heading: str) -> str:
    h = cand.hypothesis
    lines = [
        heading, "",
        _structure_table(cand), "",
        "- source: `%s`" % h.probe_name,
        "- revision_path: %s" % _path_text(h.revision_path),
    ]
    if cand.alternative_paths:
        lines.append("- alternative_paths: %s" % "; ".join(_path_text(p) for p in cand.alternative_paths))
    lines.append("- data region: [%d, %d)" % (cand.data_start, cand.data_end))
    lines.append("- trailer: %s" % (cand.trailer if cand.trailer else "none"))
    lines.append("- %s" % _closure_line(cand))
    lines.append("- %s" % _coherence_line(cand))
    return "\n".join(lines) + "\n"


def _rejection_lines(rejections) -> str:
    rejections = list(rejections or ())
    if not rejections:
        return "No hypotheses were rejected.\n"
    out = []
    for i, r in enumerate(rejections[:_MAX_REJECTIONS], 1):
        line = "%d. source `%s`, reason `%s`" % (i, r.source, r.reason)
        if r.discrepancy is not None:
            line += ", discrepancy %d" % r.discrepancy
        if r.detail:
            line += ", detail: %s" % " ".join(str(r.detail).split())
        out.append(line)
    if len(rejections) > _MAX_REJECTIONS:
        out.append("\u2026 and %d more not listed" % (len(rejections) - _MAX_REJECTIONS))
    return "\n".join(out) + "\n"


def _design_document(overview, architecture, components, models, prop, errors, testing) -> str:
    return (
        "# Design Document\n\n## Overview\n\n%s\n\n## Architecture\n\n%s\n\n"
        "## Components and Interfaces\n\n%s\n\n## Data Models\n\n%s\n\n"
        "## Correctness Properties\n\n%s\n\n## Error Handling\n\n%s\n\n"
        "## Testing Strategy\n\n%s\n"
    ) % (overview, architecture, components, models, prop, errors, testing)


def _property(title: str, text: str, validates: str) -> str:
    return "### Property 1: %s\n\n%s\n\n**Validates: Requirements %s**" % (title, text, validates)


def _error_design(message: str) -> str:
    message = " ".join(str(message).split()).rstrip(".")
    return _design_document(
        "NECROPSY could not describe this input. Error: %s." % message,
        "No structure was recovered, so there is no architecture to describe.",
        "No components were derived.",
        "No data model was derived.",
        _property("Error is reported", "The system reports that no layout was recovered.", "1.1"),
        "The error is: %s." % message,
        "No tests apply because nothing was recovered.",
    )


def _render_design(layout: dict, result) -> str:
    kind = layout.get("kind")
    if kind == "error":
        return _error_design(layout.get("error", "unknown error"))
    status = getattr(result, "status", None)
    slug = layout.get("slug")
    rejections = getattr(result, "rejections", ())
    nrej = len(rejections or ())
    errors = (
        "Every hypothesis the engine tried and rejected is listed below with its source and "
        "reason. %d rejection%s recorded.\n\n%s"
        % (nrej, "" if nrej == 1 else "s", _rejection_lines(rejections))
    )

    if kind == "ambiguous":
        cands = list(getattr(result, "candidates", ()) or ())
        if not cands:
            return _error_design("ambiguous result holds no candidates")
        n = len(cands)
        stage = getattr(result, "stage", "")
        overview = (
            "Result `%s` for slug `%s`: %d candidate layouts close, and the bytes cannot "
            "distinguish them. No candidate is preferred. Coherence is %s and does not choose."
            % (status, slug, n, _COHERENCE_LABEL)
        )
        architecture = "- stage: `%s`\n- sources: %s\n- candidates: %d" % (
            stage, ", ".join("`%s`" % c.hypothesis.probe_name for c in cands), n)
        blocks = [_candidate_block(c, "### Candidate %d" % i) for i, c in enumerate(cands, 1)]
        components = "\n".join(
            "%d. Candidate %d: data region [%d, %d), trailer %s. %s. %s." % (
                i, i, c.data_start, c.data_end, c.trailer if c.trailer else "none",
                _closure_line(c), _coherence_line(c))
            for i, c in enumerate(cands, 1))
        prop = _property(
            "Every candidate closes and none is promoted",
            "Each of the %d candidates satisfies its closure arithmetic, and no candidate is "
            "selected over another by coherence or order." % n,
            "1.1, %d.2" % (n + 1))
        testing = ("Tests target `parse_candidates`, which must return every candidate. "
                   "Each candidate is checked for field round-trip and for the closure size.")
        return _design_document(overview, architecture, components, "\n".join(blocks),
                                prop, errors, testing)

    if kind not in ("format", "file"):
        return _error_design("unsupported layout kind")
    cand = getattr(result, "candidate", None)
    if cand is None:
        return _error_design("result holds no candidate")
    h = cand.hypothesis
    overview = (
        "Result `%s` for slug `%s` (layout kind `%s`): one layout closes. The structure is "
        "%d x %d at %d bits per pixel, header size %d."
        % (status, slug, kind, h.width, h.height, h.bit_depth, h.header_size)
    )
    architecture = "- stage: `%s`\n- source: `%s`\n- revision_path: %s" % (
        getattr(result, "stage", ""), h.probe_name, _path_text(h.revision_path))
    if cand.alternative_paths:
        architecture += "\n- alternative_paths: %s" % "; ".join(
            _path_text(p) for p in cand.alternative_paths)
    components = "\n".join([
        "- data region: [%d, %d)" % (cand.data_start, cand.data_end),
        "- trailer: %s" % (cand.trailer if cand.trailer else "none"),
        "- %s" % _closure_line(cand),
        "- %s" % _coherence_line(cand),
    ])
    prop = _property(
        "Closure holds",
        "The data region decodes to exactly `row_stride` \u00d7 `height` bytes. %s." % _closure_line(cand),
        "4.1, 3.1")
    testing = ("Tests parse the embedded source and assert the observed values and closure, and "
               "check that `parse` never raises on arbitrary bytes.")
    return _design_document(overview, architecture, components, _structure_table(cand),
                            prop, errors, testing)


def render_design(layout, result, data) -> str:
    """Render the emitted design.md. Never raises."""
    try:
        return _render_design(layout, result)
    except Exception as exc:
        try:
            return _error_design("render error: " + type(exc).__name__)
        except Exception:
            return ("# Design Document\n\n## Overview\n\nRender error.\n\n## Architecture\n\nNone.\n\n"
                    "## Components and Interfaces\n\nNone.\n\n## Data Models\n\nNone.\n\n"
                    "## Correctness Properties\n\n### Property 1: Error is reported\n\n"
                    "**Validates: Requirements 1.1**\n\n## Error Handling\n\nRender error.\n\n"
                    "## Testing Strategy\n\nNone.\n")