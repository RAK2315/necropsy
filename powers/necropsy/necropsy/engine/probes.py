"""Format probes: read declared header fields and propose a seed hypothesis."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from necropsy.engine.types import FieldRecord, Hypothesis, RejectionEntry

# PCX header layout (all offsets in bytes, little-endian multi-byte fields).
PCX_HEADER_SIZE = 128
PCX_MANUFACTURER_OFFSET = 0x00   # B, must be 0x0A
PCX_ENCODING_OFFSET = 0x02       # B, 0 = none, 1 = RLE
PCX_BIT_DEPTH_OFFSET = 0x03      # B
PCX_XMIN_OFFSET = 0x04           # <H
PCX_YMIN_OFFSET = 0x06           # <H
PCX_XMAX_OFFSET = 0x08           # <H
PCX_YMAX_OFFSET = 0x0A           # <H
PCX_PLANES_OFFSET = 0x41         # B
PCX_BYTES_PER_LINE_OFFSET = 0x42  # <H
PCX_SIGNATURE = 0x0A
PCX_ENCODINGS = {0: "none", 1: "rle_pcx"}


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of a probe whose signature matched.

    `seed` is None only when the probe declines under Requirement 2.10: the
    declaration is impossible (e.g. a PCX encoding byte outside {0, 1}), so there
    is nothing to check. A declining outcome carries exactly one
    probe_precondition_failed rejection whose hypothesis is None.
    """

    seed: Hypothesis | None
    rejections: tuple[RejectionEntry, ...]


def read(data: bytes, name: str, offset: int, fmt: str) -> FieldRecord | None:
    """Safe field read. Returns None when out of bounds or on any error; never raises."""
    try:
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            return None
        return FieldRecord(name, offset, fmt, struct.unpack_from(fmt, data, offset))
    except Exception:
        return None


def probe_pcx(data: bytes) -> ProbeOutcome | None:
    """PCX probe. Returns None when the bytes do not look like a PCX header."""
    try:
        return _probe_pcx(data)
    except Exception:  # last line of defence; inner code bounds-checks
        return None


def _probe_pcx(data: bytes) -> ProbeOutcome | None:
    if len(data) < PCX_HEADER_SIZE:
        return None
    if data[PCX_MANUFACTURER_OFFSET] != PCX_SIGNATURE:
        return None
    encoding_byte = data[PCX_ENCODING_OFFSET]
    if encoding_byte not in PCX_ENCODINGS:
        # Requirement 2.10: decline; no other field is read or recorded.
        detail = (
            f"encoding byte at 0x{PCX_ENCODING_OFFSET:02X} is 0x{encoding_byte:02X}; "
            "PCX defines only 0x00 and 0x01"
        )
        return ProbeOutcome(
            None,
            (RejectionEntry("probe_precondition_failed", "pcx", None, detail=detail),),
        )

    specs = (
        ("encoding", PCX_ENCODING_OFFSET, "B"),
        ("bit_depth", PCX_BIT_DEPTH_OFFSET, "B"),
        ("xmin", PCX_XMIN_OFFSET, "<H"),
        ("ymin", PCX_YMIN_OFFSET, "<H"),
        ("xmax", PCX_XMAX_OFFSET, "<H"),
        ("ymax", PCX_YMAX_OFFSET, "<H"),
        ("planes", PCX_PLANES_OFFSET, "B"),
        ("bytes_per_line", PCX_BYTES_PER_LINE_OFFSET, "<H"),
    )
    records = {}
    for name, offset, fmt in specs:
        rec = read(data, name, offset, fmt)
        if rec is None:
            return None
        records[name] = rec

    def val(name: str) -> int:
        return records[name].value[0]

    xmin, ymin, xmax, ymax = val("xmin"), val("ymin"), val("xmax"), val("ymax")
    planar = {}
    if val("planes") > 1:
        # Requirement 6.2: the scanline is `planes` planes of bytes_per_line bytes each.
        planar = {
            "planes": val("planes"),
            "row_bytes": val("planes") * val("bytes_per_line"),
        }
    bits = val("bit_depth") * val("planes") if planar else val("bit_depth")
    seed = Hypothesis(
        width=xmax,
        height=ymax,
        bit_depth=bits,
        header_size=PCX_HEADER_SIZE,
        row_alignment=1,
        encoding=PCX_ENCODINGS[val("encoding")],
        fields=tuple(records[name] for name, _, _ in specs),
        probe_name="pcx",
        bounds=(xmin, ymin, xmax, ymax),
        **planar,
    )

    problems = []
    if xmax < xmin:
        problems.append(f"xmax {xmax} < xmin {xmin}")
    if ymax < ymin:
        problems.append(f"ymax {ymax} < ymin {ymin}")
    if val("bytes_per_line") <= 0:
        problems.append(f"bytes_per_line {val('bytes_per_line')} is not > 0")
    rejections: tuple[RejectionEntry, ...] = ()
    if problems:
        rejections = (
            RejectionEntry("probe_precondition_failed", "pcx", seed, detail="; ".join(problems)),
        )
    return ProbeOutcome(seed, rejections)


# TGA header layout (all offsets in bytes, little-endian multi-byte fields).
TGA_HEADER_SIZE = 18
TGA_ID_LENGTH_OFFSET = 0x00          # B
TGA_COLOR_MAP_TYPE_OFFSET = 0x01     # B, must be 0 or 1
TGA_IMAGE_TYPE_OFFSET = 0x02         # B
TGA_COLOR_MAP_LENGTH_OFFSET = 0x05   # <H
TGA_COLOR_MAP_ENTRY_SIZE_OFFSET = 0x07  # B, bits per colour-map entry
TGA_WIDTH_OFFSET = 0x0C              # <H
TGA_HEIGHT_OFFSET = 0x0E             # <H
TGA_BIT_DEPTH_OFFSET = 0x10          # B
TGA_IMAGE_DESCRIPTOR_OFFSET = 0x11   # B, bit 5 set = top-left origin
TGA_ENCODINGS = {1: "none", 2: "none", 3: "none", 9: "rle_tga", 10: "rle_tga", 11: "rle_tga"}


def probe_tga(data: bytes) -> ProbeOutcome | None:
    """TGA probe. Returns None when the bytes do not look like a TGA header."""
    try:
        return _probe_tga(data)
    except Exception:  # last line of defence; inner code bounds-checks
        return None


def _probe_tga(data: bytes) -> ProbeOutcome | None:
    if len(data) < TGA_HEADER_SIZE:
        return None
    if data[TGA_COLOR_MAP_TYPE_OFFSET] not in (0, 1):
        return None
    if data[TGA_IMAGE_TYPE_OFFSET] not in TGA_ENCODINGS:
        return None

    specs = (
        ("id_length", TGA_ID_LENGTH_OFFSET, "B"),
        ("color_map_type", TGA_COLOR_MAP_TYPE_OFFSET, "B"),
        ("image_type", TGA_IMAGE_TYPE_OFFSET, "B"),
        ("color_map_length", TGA_COLOR_MAP_LENGTH_OFFSET, "<H"),
        ("color_map_entry_size", TGA_COLOR_MAP_ENTRY_SIZE_OFFSET, "B"),
        ("width", TGA_WIDTH_OFFSET, "<H"),
        ("height", TGA_HEIGHT_OFFSET, "<H"),
        ("bit_depth", TGA_BIT_DEPTH_OFFSET, "B"),
        # Reported only: bit 5 set = top-left origin. Does not affect inference.
        ("image_descriptor", TGA_IMAGE_DESCRIPTOR_OFFSET, "B"),
    )
    records = {}
    for name, offset, fmt in specs:
        rec = read(data, name, offset, fmt)
        if rec is None:
            return None
        records[name] = rec

    def val(name: str) -> int:
        return records[name].value[0]

    entry_bytes = (val("color_map_entry_size") + 7) // 8
    header_size = (
        TGA_HEADER_SIZE
        + val("id_length")
        + val("color_map_type") * val("color_map_length") * entry_bytes
    )
    width, height = val("width"), val("height")
    seed = Hypothesis(
        width=width,
        height=height,
        bit_depth=val("bit_depth"),
        header_size=header_size,
        row_alignment=1,
        encoding=TGA_ENCODINGS[val("image_type")],
        fields=tuple(records[name] for name, _, _ in specs),
        probe_name="tga",
    )

    problems = []
    if width <= 0:
        problems.append(f"width {width} is not > 0")
    if height <= 0:
        problems.append(f"height {height} is not > 0")
    rejections: tuple[RejectionEntry, ...] = ()
    if problems:
        rejections = (
            RejectionEntry("probe_precondition_failed", "tga", seed, detail="; ".join(problems)),
        )
    return ProbeOutcome(seed, rejections)


# PBM (P4) text header layout. Offsets are bytes; dimensions are ASCII decimal tokens.
PBM_MIN_LENGTH = 7
PBM_SIGNATURE = b"P4\n"
PBM_MAGIC_OFFSET = 0x00     # 3s
PBM_SCAN_LIMIT = 1024       # header text is read only within data[:1024]
PBM_AFTER_MAGIC = 3         # first index after the signature


def probe_pbm(data: bytes) -> ProbeOutcome | None:
    """PBM probe. Returns None when the bytes do not start with b"P4\\n"."""
    try:
        return _probe_pbm(data)
    except Exception:  # last line of defence; inner code bounds-checks
        return None


def _parse_pbm_header(window: bytes) -> tuple[int, int, int, int, int, int, int] | str:
    """Parse the text header. Returns (width, height, header_size, w_off, w_len, h_off, h_len)
    or a failure description."""
    index = PBM_AFTER_MAGIC
    while index < len(window) and window[index : index + 1] == b"#":
        newline = window.find(b"\n", index)
        if newline < 0:
            return "comment line has no newline within the first 1024 bytes"
        index = newline + 1
    newline = window.find(b"\n", index)
    if newline < 0:
        return "dimensions line has no newline within the first 1024 bytes"
    line = window[index:newline]
    tokens = line.split()
    if len(tokens) != 2:
        return f"dimensions line has {len(tokens)} tokens, expected 2"
    if not all(token.isdigit() for token in tokens):
        return "dimensions line tokens are not all ASCII digits"
    width_rel = line.find(tokens[0])
    height_rel = line.find(tokens[1], width_rel + len(tokens[0]))
    if width_rel < 0 or height_rel < 0:
        return "could not locate dimension tokens"
    return (
        int(tokens[0]),
        int(tokens[1]),
        newline + 1,
        index + width_rel,
        len(tokens[0]),
        index + height_rel,
        len(tokens[1]),
    )


def _probe_pbm(data: bytes) -> ProbeOutcome | None:
    if len(data) < PBM_MIN_LENGTH:
        return None
    if data[PBM_MAGIC_OFFSET : PBM_MAGIC_OFFSET + 3] != PBM_SIGNATURE:
        return None

    window = data[:PBM_SCAN_LIMIT]
    magic = read(data, "magic", PBM_MAGIC_OFFSET, "3s")
    if magic is None:
        return None

    parsed = _parse_pbm_header(window)
    if isinstance(parsed, str):
        seed = Hypothesis(
            width=0,
            height=0,
            bit_depth=1,
            header_size=PBM_AFTER_MAGIC,
            row_alignment=1,
            encoding="none",
            fields=(magic,),
            probe_name="pbm",
        )
        return ProbeOutcome(
            seed, (RejectionEntry("probe_precondition_failed", "pbm", seed, detail=parsed),)
        )

    width, height, header_size, w_off, w_len, h_off, h_len = parsed
    width_rec = read(data, "width", w_off, f"{w_len}s")
    height_rec = read(data, "height", h_off, f"{h_len}s")
    if width_rec is None or height_rec is None:
        return None
    seed = Hypothesis(
        width=width,
        height=height,
        bit_depth=1,
        header_size=header_size,
        row_alignment=1,
        encoding="none",
        fields=(magic, width_rec, height_rec),
        probe_name="pbm",
    )

    problems = []
    if width <= 0:
        problems.append(f"width {width} is not > 0")
    if height <= 0:
        problems.append(f"height {height} is not > 0")
    rejections: tuple[RejectionEntry, ...] = ()
    if problems:
        rejections = (
            RejectionEntry("probe_precondition_failed", "pbm", seed, detail="; ".join(problems)),
        )
    return ProbeOutcome(seed, rejections)


# TIFF header layout. "o" is "<" for b"II" and ">" for b"MM"; offsets are bytes.
TIFF_MIN_LENGTH = 8
TIFF_BYTE_ORDER_OFFSET = 0x00   # 2s, b"II" or b"MM"
TIFF_MAGIC_OFFSET = 0x02        # oH, must be 42
TIFF_IFD_OFFSET_OFFSET = 0x04   # oI
TIFF_MAGIC = 42
TIFF_ORDERS = {b"II": "<", b"MM": ">"}
TIFF_ENTRY_SIZE = 12
TIFF_ENTRY_TAG_OFFSET = 0       # oH
TIFF_ENTRY_TYPE_OFFSET = 2      # oH
TIFF_ENTRY_COUNT_OFFSET = 4     # oI
TIFF_ENTRY_VALUE_OFFSET = 8     # oH for SHORT (3), oI for LONG (4)
TIFF_TAG_NAMES = {
    256: "width",
    257: "height",
    258: "bits_per_sample",
    259: "compression",
    278: "rows_per_strip",
    262: "photometric_interpretation",   # optional; reported only, never in the seed
    273: "strip_offset",
    277: "samples_per_pixel",
    279: "strip_byte_count",
    284: "planar_configuration",
}
TIFF_BITS_PER_SAMPLE_TAG = 258
TIFF_MAX_SAMPLES = 32           # largest BitsPerSample count the probe reads
TIFF_VALUE_FIELD_SIZE = 4       # bytes in an entry's value field (entry + 8)
TIFF_TYPE_SIZES = {3: 2, 4: 4}  # bytes per SHORT (3) and LONG (4) value
TIFF_REQUIRED_TAGS = (256, 257, 258, 273, 279)
TIFF_TYPE_FORMATS = {3: "H", 4: "I"}
TIFF_ROWS_PER_STRIP_TAG = 278   # SHORT or LONG, count 1; absent = 2^32 - 1
TIFF_STRIP_OFFSET_TAG = 273
TIFF_STRIP_BYTE_COUNT_TAG = 279
TIFF_TILE_OFFSET_TAG = 324      # presence only here; tiles are read by a later task
TIFF_MAX_RANGES = 16384         # largest strip array count the probe reads
TIFF_ROWS_PER_STRIP_DEFAULT = 2**32 - 1
TIFF_ARRAY_NAMES = {273: "strip_offset", 279: "strip_byte_count"}


def _read_range_array(
    data: bytes, order: str, entry: int, type_id: int, n: int, name: str
) -> tuple[list[FieldRecord], str, str]:
    """Read a strip array (tags 273, 279). Returns (records, problem_kind, detail).

    problem_kind is "" on success, "bounds" or "precondition". Records are named
    `name[i]` and returned only on success. Nothing is allocated from `n` before
    it has passed the 1..TIFF_MAX_RANGES check.
    """
    size = TIFF_TYPE_SIZES[type_id]
    fmt = order + TIFF_TYPE_FORMATS[type_id]
    if n < 1 or n > TIFF_MAX_RANGES:
        return [], "precondition", (
            f"{name} count {n} is outside 1..{TIFF_MAX_RANGES}; values not read"
        )
    start = entry + TIFF_ENTRY_VALUE_OFFSET
    if n * size > TIFF_VALUE_FIELD_SIZE:
        pointer = read(data, f"{name}_offset", start, order + "I")
        if pointer is None:
            return [], "bounds", f"{name} offset field runs past the end of the data"
        start = pointer.value[0]
    records = []
    for i in range(n):
        rec = read(data, f"{name}[{i}]", start + size * i, fmt)
        if rec is None:
            return [], "bounds", (
                f"{name} value {i} of {n} at offset {start + size * i} lies outside the data"
            )
        records.append(rec)
    return records, "", ""


def _read_bits_per_sample(
    data: bytes, order: str, entry: int, type_id: int, n: int
) -> tuple[list[FieldRecord], str, str]:
    """Read the BitsPerSample array. Returns (records, problem_kind, detail).

    problem_kind is "" on success, "bounds" or "precondition" otherwise; records are
    returned only on success or on the unequal-values precondition failure.
    """
    size = TIFF_TYPE_SIZES[type_id]
    fmt = order + TIFF_TYPE_FORMATS[type_id]
    if n < 1 or n > TIFF_MAX_SAMPLES:
        return [], "precondition", (
            f"bits_per_sample count {n} is outside 1..{TIFF_MAX_SAMPLES}; values not read"
        )
    start = entry + TIFF_ENTRY_VALUE_OFFSET
    if n * size > TIFF_VALUE_FIELD_SIZE:
        pointer = read(data, "bits_per_sample_offset", start, order + "I")
        if pointer is None:
            return [], "bounds", "bits_per_sample offset field runs past the end of the data"
        start = pointer.value[0]
    records = []
    for i in range(n):
        rec = read(data, "bits_per_sample", start + size * i, fmt)
        if rec is None:
            return [], "bounds", (
                f"bits_per_sample value {i} of {n} at offset {start + size * i} "
                "lies outside the data"
            )
        records.append(rec)
    return records, "", ""


def probe_tiff(data: bytes) -> ProbeOutcome | None:
    """TIFF probe. Returns None when the bytes do not look like a TIFF header."""
    try:
        return _probe_tiff(data)
    except Exception:  # last line of defence; inner code bounds-checks
        return None


def _probe_tiff(data: bytes) -> ProbeOutcome | None:
    if len(data) < TIFF_MIN_LENGTH:
        return None
    order = TIFF_ORDERS.get(bytes(data[TIFF_BYTE_ORDER_OFFSET : TIFF_BYTE_ORDER_OFFSET + 2]))
    if order is None:
        return None
    magic = read(data, "magic", TIFF_MAGIC_OFFSET, order + "H")
    if magic is None or magic.value[0] != TIFF_MAGIC:
        return None
    byte_order = read(data, "byte_order", TIFF_BYTE_ORDER_OFFSET, "2s")
    ifd = read(data, "ifd_offset", TIFF_IFD_OFFSET_OFFSET, order + "I")
    if byte_order is None or ifd is None:
        return None

    records = [byte_order, magic, ifd]
    values: dict[int, int] = {}
    out_of_bounds = ""
    bps_seen = False
    bps_problems: list[str] = []
    bps_unestablished = False
    arrays: dict[int, list[FieldRecord]] = {}   # tags 273 / 279 with count != 1
    array_attempted: set[int] = set()
    array_problems: list[str] = []
    seen_tags: set[int] = set()
    ifd_offset = ifd.value[0]
    count_rec = read(data, "ifd_entry_count", ifd_offset, order + "H")
    if count_rec is None:
        out_of_bounds = f"ifd_offset {ifd_offset} leaves no room for the entry count"
    else:
        records.append(count_rec)
        entry_count = count_rec.value[0]
        for k in range(entry_count):
            entry = ifd_offset + 2 + TIFF_ENTRY_SIZE * k
            if entry + TIFF_ENTRY_SIZE > len(data):
                out_of_bounds = (
                    f"entry {k} of {entry_count} at offset {entry} runs past the end of the data"
                )
                break
            tag = read(data, "tag", entry + TIFF_ENTRY_TAG_OFFSET, order + "H")
            kind = read(data, "type", entry + TIFF_ENTRY_TYPE_OFFSET, order + "H")
            count = read(data, "count", entry + TIFF_ENTRY_COUNT_OFFSET, order + "I")
            if tag is None or kind is None or count is None:
                continue
            tag_id, type_id = tag.value[0], kind.value[0]
            seen_tags.add(tag_id)
            if (tag_id in TIFF_ARRAY_NAMES and count.value[0] != 1
                    and type_id in TIFF_TYPE_SIZES):
                if tag_id in array_attempted or tag_id in values:
                    continue
                array_attempted.add(tag_id)
                recs, kind_, detail = _read_range_array(
                    data, order, entry, type_id, count.value[0], TIFF_ARRAY_NAMES[tag_id]
                )
                if kind_ == "bounds":
                    out_of_bounds = out_of_bounds or detail
                elif kind_ == "precondition":
                    array_problems.append(detail)
                else:
                    arrays[tag_id] = recs
                    records.extend(recs)
                continue
            if tag_id == TIFF_BITS_PER_SAMPLE_TAG:
                if bps_seen or type_id not in TIFF_TYPE_SIZES:
                    continue
                bps_seen = True
                recs, kind_, detail = _read_bits_per_sample(
                    data, order, entry, type_id, count.value[0]
                )
                if kind_ == "bounds":
                    out_of_bounds = out_of_bounds or detail
                elif kind_ == "precondition":
                    bps_problems.append(detail)
                    bps_unestablished = True
                else:
                    records.extend(recs)
                    distinct = sorted({r.value[0] for r in recs})
                    if len(distinct) == 1:
                        values[tag_id] = distinct[0]
                    else:
                        bps_problems.append(
                            "bits_per_sample values are not all equal: "
                            + ", ".join(str(r.value[0]) for r in recs)
                        )
                        bps_unestablished = True
                continue
            if tag_id not in TIFF_TAG_NAMES or count.value[0] != 1:
                continue
            code = TIFF_TYPE_FORMATS.get(type_id)
            if code is None or tag_id in values or tag_id in array_attempted:
                continue
            rec = read(data, TIFF_TAG_NAMES[tag_id], entry + TIFF_ENTRY_VALUE_OFFSET, order + code)
            if rec is None:
                continue
            records.append(rec)
            values[tag_id] = rec.value[0]

    compression = values.get(259, 1)
    samples = values.get(277, 1)
    planar = values.get(284, 1)
    height = values.get(257, 0)
    rps_declared = values.get(TIFF_ROWS_PER_STRIP_TAG, TIFF_ROWS_PER_STRIP_DEFAULT)
    offsets_list = [r.value[0] for r in arrays.get(273, [])]
    counts_list = [r.value[0] for r in arrays.get(279, [])]
    if 279 in values and 279 not in arrays:
        counts_list = [values[279]]
    multi = len(offsets_list) > 1
    ranges: tuple[tuple[int, int], ...] = ()
    rows_per_strip = None
    strip_offset = values.get(273, 0)
    data_end = strip_offset + values.get(279, 0)
    if multi:
        ranges = tuple((o, o + c) for o, c in zip(offsets_list, counts_list))
        rows_per_strip = min(rps_declared, height)
        if ranges:
            strip_offset = min(s for s, _ in ranges)
            data_end = max(e for _, e in ranges)
    seed = Hypothesis(
        width=values.get(256, 0),
        height=height,
        bit_depth=values.get(258, 0) * samples,
        header_size=strip_offset,
        row_alignment=1,
        encoding="none" if compression == 1 else f"tiff_compression_{compression}",
        data_end=data_end,
        fields=tuple(records),
        probe_name="tiff",
        ranges=ranges,
        rows_per_strip=rows_per_strip,
    )

    rejections: list[RejectionEntry] = []
    if out_of_bounds:
        rejections.append(
            RejectionEntry("field_out_of_bounds", "tiff", seed, detail=out_of_bounds)
        )
    problems = []
    missing = [
        TIFF_TAG_NAMES[t]
        for t in TIFF_REQUIRED_TAGS
        if t not in values and t not in arrays and t not in array_attempted
        and not (t == TIFF_BITS_PER_SAMPLE_TAG and bps_unestablished)
    ]
    if missing:
        problems.append("missing tags: " + ", ".join(missing))
    problems.extend(bps_problems)
    problems.extend(array_problems)
    n_off = len(offsets_list) if offsets_list else (1 if 273 in values else 0)
    n_cnt = len(counts_list)
    if n_off and n_cnt and n_off != n_cnt:
        problems.append(
            f"strip_offset count {n_off} differs from strip_byte_count count {n_cnt}"
        )
    if n_off and 256 in values and 257 in values:
        if rps_declared < 1:
            problems.append("rows_per_strip is 0")
        else:
            want = -(-height // min(rps_declared, height)) if height > 0 else 0
            if n_off != want:
                problems.append(
                    f"strip count {n_off} differs from ceil(height {height} / "
                    f"rows_per_strip {min(rps_declared, height)}) = {want}"
                )
    if TIFF_TILE_OFFSET_TAG in seen_tags and TIFF_STRIP_OFFSET_TAG in seen_tags:
        problems.append("tags 273 (strip_offset) and 324 (tile_offset) are both present")
    if planar != 1:
        problems.append(f"planar_configuration {planar} is not 1")
    if problems:
        rejections.append(
            RejectionEntry("probe_precondition_failed", "tiff", seed, detail="; ".join(problems))
        )
    return ProbeOutcome(seed, tuple(rejections))


# PNM header (binary P5, P6). Text grammar read only within data[:1024].
PNM_MIN_LENGTH = 4
PNM_MAGIC_OFFSET = 0x00            # 2s: b"P" then one of 1 2 3 5 6
PNM_SIGNATURE_BYTE = 0x50          # "P"
PNM_FIRST_SEPARATOR_OFFSET = 0x02  # must be ASCII whitespace
PNM_SCAN_LIMIT = 1024
PNM_WHITESPACE = frozenset(b" \t\n\x0b\x0c\r")
PNM_DIGITS = frozenset(b"0123456789")
PNM_MAGIC_DIGITS = frozenset(b"12356")
PNM_BINARY = {0x35: 8, 0x36: 24}   # "5" -> grey, "6" -> RGB: bits per pixel at maxval <= 255
PNM_TEXT = {0x31: 1, 0x32: 8, 0x33: 24}  # "1" -> bits, "2" -> grey, "3" -> RGB (pnm_text)
PNM_MAX_MAXVAL = 65535


def probe_pnm(data: bytes) -> ProbeOutcome | None:
    """PNM probe (binary P5 and P6). Returns None when the signature does not match."""
    try:
        return _probe_pnm(data)
    except Exception:  # last line of defence; inner code bounds-checks
        return None


def _pnm_skip(window: bytes, index: int) -> tuple[int, bool, str]:
    """Skip whitespace and comments from index. Returns (index, saw_separator, problem)."""
    saw = False
    n = len(window)
    while index < n:
        b = window[index]
        if b in PNM_WHITESPACE:
            saw = True
            index += 1
        elif b == 0x23:  # "#": comment through the next 0x0A or 0x0D
            end = index + 1
            while end < n and window[end] not in (0x0A, 0x0D):
                end += 1
            if end >= n:
                return index, saw, "comment has no line end within the first 1024 bytes"
            saw = True
            index = end + 1
        else:
            break
    return index, saw, ""


def _pnm_token(window: bytes, index: int) -> tuple[int, int]:
    """Run of ASCII digits from index. Returns (end_index, value); value is -1 for no digits."""
    end = index
    while end < len(window) and window[end] in PNM_DIGITS:
        end += 1
    if end == index:
        return end, -1
    return end, int(window[index:end])


def _probe_pnm(data: bytes) -> ProbeOutcome | None:
    if len(data) < PNM_MIN_LENGTH:
        return None
    if data[0] != PNM_SIGNATURE_BYTE or data[1] not in PNM_MAGIC_DIGITS:
        return None
    if data[PNM_FIRST_SEPARATOR_OFFSET] not in PNM_WHITESPACE:
        return None
    is_text = data[1] in PNM_TEXT
    is_p1 = data[1] == 0x31

    magic = read(data, "magic", PNM_MAGIC_OFFSET, "2s")
    if magic is None:
        return None
    bits = PNM_TEXT[data[1]] if is_text else PNM_BINARY[data[1]]
    window = data[:PNM_SCAN_LIMIT]
    records = [magic]
    values: dict[str, int] = {}
    problems: list[str] = []
    header_size = PNM_FIRST_SEPARATOR_OFFSET
    index = PNM_FIRST_SEPARATOR_OFFSET
    names = ("width", "height") if is_p1 else ("width", "height", "maxval")
    for name in names:
        index, saw, problem = _pnm_skip(window, index)
        if problem:
            problems.append(problem)
            break
        if not saw:
            problems.append(f"no whitespace before {name}")
            break
        end, value = _pnm_token(window, index)
        if value < 0 or (end >= len(window) and len(data) > len(window)):
            problems.append(f"{name} is not a complete run of ASCII digits")
            break
        rec = read(data, name, index, f"{end - index}s")
        if rec is None:
            problems.append(f"{name} lies outside the data")
            break
        records.append(rec)
        values[name] = value
        index = end
        header_size = end
    else:
        if is_text:
            pass  # text PNM: header ends after the last token, no whitespace byte consumed
        elif index < len(data) and data[index] in PNM_WHITESPACE:
            header_size = index + 1
        else:
            problems.append("no single whitespace byte after maxval")

    width = values.get("width", 0)
    height = values.get("height", 0)
    maxval = values.get("maxval", 0)
    if "width" in values and width == 0:
        problems.append("width 0 is not > 0")
    if "height" in values and height == 0:
        problems.append("height 0 is not > 0")
    if "maxval" in values and not 1 <= maxval <= PNM_MAX_MAXVAL:
        problems.append(f"maxval {maxval} is outside 1..{PNM_MAX_MAXVAL}")
        maxval = 0
    bit_depth = 0
    if is_p1:
        bit_depth = 1
        maxval = 1
    elif maxval:
        bit_depth = bits if maxval <= 255 else bits * 2
    seed = Hypothesis(
        width=width,
        height=height,
        bit_depth=bit_depth,
        header_size=header_size,
        row_alignment=1,
        encoding="pnm_text" if is_text else "none",
        fields=tuple(records),
        probe_name="pnm",
        maxval=1 if is_p1 else (maxval if "maxval" in values else None),
    )
    rejections: tuple[RejectionEntry, ...] = ()
    if problems:
        rejections = (
            RejectionEntry("probe_precondition_failed", "pnm", seed, detail="; ".join(problems)),
        )
    return ProbeOutcome(seed, rejections)


PROBES = (
    ("pcx", probe_pcx),
    ("tga", probe_tga),
    ("pbm", probe_pbm),
    ("pnm", probe_pnm),
    ("tiff", probe_tiff),
)