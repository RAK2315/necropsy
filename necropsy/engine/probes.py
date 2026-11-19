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
    seed: Hypothesis
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
    if data[PCX_ENCODING_OFFSET] not in PCX_ENCODINGS:
        return None

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
    seed = Hypothesis(
        width=xmax,
        height=ymax,
        bit_depth=val("bit_depth"),
        header_size=PCX_HEADER_SIZE,
        row_alignment=1,
        encoding=PCX_ENCODINGS[val("encoding")],
        fields=tuple(records[name] for name, _, _ in specs),
        probe_name="pcx",
        bounds=(xmin, ymin, xmax, ymax),
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
    273: "strip_offset",
    277: "samples_per_pixel",
    279: "strip_byte_count",
}
TIFF_REQUIRED_TAGS = (256, 257, 258, 273, 279)
TIFF_TYPE_FORMATS = {3: "H", 4: "I"}


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
            if tag_id not in TIFF_TAG_NAMES or count.value[0] != 1:
                continue
            code = TIFF_TYPE_FORMATS.get(type_id)
            if code is None or tag_id in values:
                continue
            rec = read(data, TIFF_TAG_NAMES[tag_id], entry + TIFF_ENTRY_VALUE_OFFSET, order + code)
            if rec is None:
                continue
            records.append(rec)
            values[tag_id] = rec.value[0]

    compression = values.get(259, 1)
    samples = values.get(277, 1)
    strip_offset = values.get(273, 0)
    seed = Hypothesis(
        width=values.get(256, 0),
        height=values.get(257, 0),
        bit_depth=values.get(258, 0) * samples,
        header_size=strip_offset,
        row_alignment=1,
        encoding="none" if compression == 1 else f"tiff_compression_{compression}",
        data_end=strip_offset + values.get(279, 0),
        fields=tuple(records),
        probe_name="tiff",
    )

    rejections: list[RejectionEntry] = []
    if out_of_bounds:
        rejections.append(
            RejectionEntry("field_out_of_bounds", "tiff", seed, detail=out_of_bounds)
        )
    problems = []
    missing = [TIFF_TAG_NAMES[t] for t in TIFF_REQUIRED_TAGS if t not in values]
    if missing:
        problems.append("missing tags: " + ", ".join(missing))
    if samples != 1:
        problems.append(f"samples_per_pixel {samples} is not 1")
    if problems:
        rejections.append(
            RejectionEntry("probe_precondition_failed", "tiff", seed, detail="; ".join(problems))
        )
    return ProbeOutcome(seed, tuple(rejections))


PROBES = (
    ("pcx", probe_pcx),
    ("tga", probe_tga),
    ("pbm", probe_pbm),
    ("tiff", probe_tiff),
)