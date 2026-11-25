"""Data types for the structure-inference engine. No logic beyond hypothesis_key."""

from __future__ import annotations

from dataclasses import dataclass, field

REASONS = frozenset({
    "arithmetic_mismatch", "decoder_overrun", "decoder_underrun", "decoder_unconsumed",
    "degenerate_hypothesis", "field_out_of_bounds", "probe_precondition_failed",
    "unsupported_encoding", "input_too_short", "internal_error",
})

TERMINATIONS = frozenset({
    "exhausted", "no_hypothesis_checked", "deadline_exceeded", "search_cap_exceeded", "input_too_short", "internal_error",
})

AMBIGUITY_REASON = (
    "{n} candidates pass closure; the bytes cannot separate them. "
    "Coherence scores are a heuristic and do not choose."
)


@dataclass(frozen=True)
class FieldRecord:
    name: str
    offset: int
    fmt: str            # struct format with explicit "<" or ">" for multi-byte reads
    value: tuple        # exactly what struct.unpack_from returned


@dataclass(frozen=True)
class Hypothesis:
    width: int
    height: int
    bit_depth: int
    header_size: int
    row_alignment: int = 1                 # 1, 2 or 4
    encoding: str = "none"
    data_end: int | None = None            # declared data end (TIFF); None means trailer registry, then EOF
    fields: tuple[FieldRecord, ...] = ()
    probe_name: str = "generic"            # "pcx" | "tga" | "pbm" | "tiff" | "generic"
    bounds: tuple[int, int, int, int] | None = None   # (xmin, ymin, xmax, ymax), PCX only
    revision_path: tuple[str, ...] = ()
    planes: int = 1                        # colour planes per scanline (PCX)
    row_bytes: int | None = None           # declared scanline bytes; replaces the derived stride
    ranges: tuple[tuple[int, int], ...] = ()   # several data ranges [start, end)
    rows_per_strip: int | None = None
    tile: tuple[int, int] | None = None    # (TileWidth, TileLength)
    maxval: int | None = None              # PNM declared maximum sample value


def hypothesis_key(h: Hypothesis) -> tuple:
    base = (h.width, h.height, h.bit_depth, h.header_size, h.row_alignment, h.encoding, h.data_end)
    extra = (h.planes, h.row_bytes, h.ranges, h.rows_per_strip, h.tile, h.maxval)
    if extra == (1, None, (), None, None, None):
        return base
    return base + (extra,)


@dataclass(frozen=True)
class RejectionEntry:
    reason: str                            # member of REASONS
    source: str                            # probe name, "revision:" + "->".join(path), or "generic"
    hypothesis: Hypothesis | None = None
    discrepancy: int | None = None         # arithmetic_mismatch only
    detail: str = ""


@dataclass(frozen=True)
class Candidate:
    hypothesis: Hypothesis
    row_stride: int
    expected_decoded_bytes: int
    data_start: int
    data_end: int
    trailer: str | None
    coherence_score: float | None
    coherence_status: str                  # "scored" | "unscorable" | "not_computed"
    coherence_method: str = "row_mad_ratio"
    alternative_paths: tuple[tuple[str, ...], ...] = ()   # same-depth routes to this key; informational only
    decoded: bytes = field(default=b"", repr=False)
    ranges: tuple[tuple[int, int], ...] = ()   # ranges that closed, in order


@dataclass(frozen=True)
class VerifiedHypothesis:
    candidate: Candidate
    stage: str                             # "probe" | "revision" | "generic"
    rejections: tuple[RejectionEntry, ...]
    total_checks: int
    total_file_size: int
    status: str = "RESOLVED"


@dataclass(frozen=True)
class AmbiguousResult:
    candidates: tuple[Candidate, ...]      # discovery order, >= 2, distinct keys
    stage: str
    reason: str
    coherence_gap: float | None
    rejections: tuple[RejectionEntry, ...]
    total_checks: int
    total_file_size: int
    status: str = "UNRESOLVED_AMBIGUITY"


@dataclass(frozen=True)
class FailureReport:
    termination: str                       # member of TERMINATIONS
    rejections: tuple[RejectionEntry, ...]
    total_checks: int
    total_file_size: int
    partial_candidates: tuple[Candidate, ...] = ()
    status: str = "FAILED"


EngineResult = VerifiedHypothesis | AmbiguousResult | FailureReport
