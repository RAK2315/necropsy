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
