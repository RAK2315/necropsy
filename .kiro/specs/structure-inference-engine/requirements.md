# Requirements Document

## Introduction

The Structure-Inference Engine is the core reasoning component of NECROPSY. Given an arbitrary sequence of bytes with no extension or format declaration, the engine hypothesises a binary image structure, verifies the hypothesis against a closure gate, applies an ordered composition of revision strategies when closure fails, and returns either a verified hypothesis or an explicit failure report listing every hypothesis tried and each rejection reason. The engine never guesses; it only returns what it can verify.

## Glossary

- **Engine**: The Structure-Inference Engine — the top-level component that accepts raw bytes and returns a `HypothesisResult`.
- **Hypothesis**: A candidate structural interpretation of a byte sequence, consisting of a header layout (named fields with byte offsets and struct formats), computed image dimensions, bit depth, header length, row padding, and encoding.
- **Encoding**: The compression scheme applied to the pixel data region. Defined values: `"none"` (uncompressed) and `"rle_pcx"` (PCX run-length encoding).
- **Closure**: The property that decoding the data region under the declared encoding produces exactly `row_stride × height` bytes. For `"none"` encoding this reduces to `header_size + row_stride × height == total_file_size`. For `"rle_pcx"` encoding the PCX RLE decoder is run against bytes from `header_size` onward; the decoded output must be exactly `row_stride × height` bytes.
- **Row stride**: The number of bytes per image row: `floor(width × bit_depth / 8) + row_padding` for `bit_depth ≥ 8`; `ceil(width × bit_depth / 8) + row_padding` for `bit_depth < 8`.
- **Revision Strategy**: A deterministic transformation applied to a Hypothesis to produce a new candidate. Defined strategies: `inclusive_bounds`, `endianness_flip`, `header_length_scan`, `row_padding_variants`, `rle_pcx`.
- **Revision Path**: An ordered list of strategy names applied in sequence to reach a passing Hypothesis. Recorded in the `VerifiedHypothesis` as `revision_path: list[str]`. Empty list means the initial probe hypothesis closed without revision.
- **Strategy Composition**: The process of applying sequences of Revision Strategies of increasing depth to a base Hypothesis until closure holds or the search cap is reached.
- **HypothesisResult**: The Engine's return value — either a `VerifiedHypothesis` or a `FailureReport`.
- **VerifiedHypothesis**: A Hypothesis that has passed the closure gate, annotated with the offset, struct format, and extracted value of every field, the `revision_path`, and the probe name that generated the base Hypothesis (or `"generic"` if no probe matched).
- **FailureReport**: A structured record listing every Hypothesis tried, its rejection reason, the closure failure details, and the strategy sequence that produced it.
- **Field**: A named value extracted from the byte sequence at a specific byte offset using an explicit struct format string.
- **FieldRecord**: A record storing field name (string), byte offset (int), struct format string (string), and extracted value as the tuple returned directly by `struct.unpack_from` without unpacking.
- **Probe**: An initial, format-specific attempt to build a Hypothesis directly from the byte sequence before any revision strategy is applied.
- **Generic Search**: The fallback path taken when no probe matches. Enumerates combinations of candidate header lengths, field offsets, field widths (uint8/uint16/uint32), and endianness, applying the closure gate to each.
- **Pretty_Printer**: A utility that renders a `HypothesisResult` as a human-readable string; it has no side effects and does not modify the result.
- **RejectionEntry**: One record in a `FailureReport`'s list, carrying the Hypothesis parameters, field records, closure failure details, and the probe name or strategy sequence that produced it.
- **Deadline**: A wall-clock time limit for the entire inference run, default 5 seconds, configurable at Engine construction time. On expiry the Engine returns a `FailureReport` with `reason = "deadline_exceeded"` listing all hypotheses tried so far. The Engine never returns a partial or unverified result after deadline expiry.
- **Search cap**: A secondary limit of 10,000 total closure checks across the Revision Phase and Generic Search combined. Prevents infinite loops on pathological inputs where individual checks are fast. Returns `FailureReport` with `reason = "search_cap_exceeded"` if reached before the deadline.

---

## Requirements

### Requirement 1: Closure Gate

**User Story:** As a developer integrating the Engine into NECROPSY, I want the Engine to reject any Hypothesis whose declared encoding does not produce the exact expected decoded output, so that the system never returns a structurally inconsistent interpretation.

#### Acceptance Criteria

1. WHEN a Hypothesis specifies `width`, `height`, `bit_depth`, `header_size`, `row_padding`, and `encoding == "none"`, THE Engine SHALL compute `row_stride` as `floor(width × bit_depth / 8) + row_padding` for `bit_depth ≥ 8` or `ceil(width × bit_depth / 8) + row_padding` for `bit_depth < 8`, and accept the Hypothesis only when `header_size + row_stride × height == total_file_size`.

2. WHEN a Hypothesis specifies `encoding == "rle_pcx"`, THE Engine SHALL run the PCX RLE decoder against the bytes beginning at offset `header_size`; the Hypothesis is accepted only when the decoder produces exactly `row_stride × height` output bytes without overrunning the input region or terminating early.

3. IF a Hypothesis fails the closure check, THEN THE Engine SHALL record a `RejectionEntry` containing: the Hypothesis parameters (`width`, `height`, `bit_depth`, `header_size`, `row_padding`, `encoding`), the struct format string and byte offset of every extracted field, and a rejection reason stating the specific failure — one of: `arithmetic_mismatch` (with discrepancy `total_file_size − (header_size + row_stride × height)`), `decoder_overrun`, or `decoder_underrun`.

4. THE Engine SHALL treat the closure gate as binary: a Hypothesis that does not close is rejected unconditionally, regardless of any plausibility score.

5. THE Engine SHALL state every field offset and struct format string explicitly in the `VerifiedHypothesis`; no field may appear without a declared offset and format.

6. WHEN `encoding == "rle_pcx"`, THE RLE decoder SHALL accept a `max_output_bytes` parameter equal to `row_stride × height` and SHALL abort immediately if the decoded output would exceed `max_output_bytes`, returning a `decoder_overrun` failure rather than allocating unbounded memory.

7. THE Engine SHALL accept a `deadline_seconds` configuration parameter (default 5.0). THE Engine SHALL check elapsed wall-clock time before each closure check; IF the deadline has been reached, THE Engine SHALL immediately return a `FailureReport` with `reason = "deadline_exceeded"` and the rejection list accumulated so far, without attempting any further checks.

---

### Requirement 2: Initial Probe Set

**User Story:** As a user dropping an unknown file into NECROPSY, I want the Engine to attempt a set of well-defined initial structure guesses before invoking revision strategies, so that common formats are identified quickly.

#### Acceptance Criteria

1. THE Engine SHALL attempt the following four Probes in order before invoking any Revision Strategy or Generic Search:

   **PCX Probe** — Signature: byte 0x00 == 0x0A and byte 0x02 ∈ {0x00, 0x01}; minimum file length 128 bytes. Fields read as literal raw values with no per-format arithmetic applied:
   - `xmin` at 0x04 as `<H`
   - `ymin` at 0x06 as `<H`
   - `xmax` at 0x08 as `<H`
   - `ymax` at 0x0A as `<H`
   - `bit_depth` at 0x03 as `B`
   - `planes` at 0x41 as `B`
   - `bytes_per_line` at 0x42 as `<H`

   Initial Hypothesis: `width = xmax`, `height = ymax`, `header_size = 128`, `encoding = "none"` when byte 0x02 == 0x00; `encoding = "rle_pcx"` when byte 0x02 == 0x01. Closure condition additionally requires `xmax ≥ xmin`, `ymax ≥ ymin`, and `bytes_per_line > 0`; if any fails, record a `RejectionEntry` and skip to the next probe.

   **TGA Probe** — Signature: `image_type` at 0x02 as `B` ∈ {1, 2, 3, 9, 10, 11}; minimum file length `18 + id_length` bytes where `id_length` is the byte at 0x00 as `B`. Fields:
   - `id_length` at 0x00 as `B`
   - `image_type` at 0x02 as `B`
   - `width` at 0x0C as `<H`
   - `height` at 0x0E as `<H`
   - `bit_depth` at 0x10 as `B`

   Initial Hypothesis: `header_size = 18 + id_length`, `encoding = "none"`. Closure additionally requires `width > 0` and `height > 0`.

   **PBM Probe** — Signature: bytes 0–2 == ASCII `P4\n`; minimum file length 7 bytes. Width and height parsed as ASCII decimal integers from the header text following the magic line; comment lines beginning with `#` are skipped; `bit_depth` fixed at 1; `row_stride = ceil(width / 8)`. Initial Hypothesis: `header_size` = byte length of the ASCII header through and including the final newline before the binary data, `encoding = "none"`. Closure additionally requires `width > 0` and `height > 0`.

   **TIFF Probe** — Signature: bytes 0–1 ∈ {`b'II'`, `b'MM'`} AND the uint16 at offset 0x02 read in the declared byte order (little-endian for `II`, big-endian for `MM`) == 42. Fields read naively as little-endian regardless of the byte order mark:
   - `ifd_offset` at 0x04 as `<I`
   - At `ifd_offset`: IFD entry count as `<H`, then entries searched for tags 256 (`<H`/`<I` value depending on type), 257, 258, 273, 279
   - `width` from tag 256, `height` from tag 257, `bit_depth` from tag 258, `strip_offset` from tag 273, `strip_byte_count` from tag 279

   Initial Hypothesis: `header_size = strip_offset`, `encoding = "none"`. Closure condition: `strip_offset + strip_byte_count == total_file_size` AND decoded bytes == `row_stride × height`. If `ifd_offset` or any tag offset falls outside `[0, total_file_size)`, record a `RejectionEntry` with reason `field_out_of_bounds` and continue.

2. IF a Probe's file length is less than that Probe's minimum header length, THEN THE Engine SHALL treat it as a signature mismatch and skip it without recording a `RejectionEntry`.

3. WHEN a Probe's signature check does not match, THE Engine SHALL skip that Probe without recording a `RejectionEntry`.

4. WHEN a Probe's signature matches but closure fails, THE Engine SHALL record a `RejectionEntry` with the probe name and failure reason, then continue to the next Probe.

---

### Requirement 3: Revision Strategy Composition

**User Story:** As a developer, I want the Engine to search over ordered compositions of revision strategies, up to a bounded depth, before declaring failure, so that multi-strategy solutions like ["inclusive_bounds", "rle_pcx"] are found while the search remains tractable.

#### Acceptance Criteria

1. WHEN all Probes have been attempted and at least one generated a rejected Hypothesis (i.e., signature matched but closure failed), THE Engine SHALL enter the Revision Phase with the set of rejected Hypotheses as the seed pool.

2. THE Engine SHALL search strategy sequences breadth-first by depth. At depth 1 it tries every single strategy against every seed Hypothesis. At depth 2 it tries every two-strategy sequence against every seed Hypothesis. At depth 3 it tries every three-strategy sequence. The search halts at depth 3.

3. THE defined Revision Strategies, each of which transforms a Hypothesis into one or more candidate Hypotheses, are:

   **inclusive_bounds** — Applies only to Hypotheses with `xmin`, `ymin`, `xmax`, `ymax` fields. Produces one new Hypothesis: `width = xmax − xmin + 1`, `height = ymax − ymin + 1`, all other parameters unchanged.

   **endianness_flip** — Swaps the byte order of every multi-byte field in the Hypothesis simultaneously. For each field with a little-endian format (`<H`, `<I`, `<i`), re-reads it at the same offset with the corresponding big-endian format (`>H`, `>I`, `>i`), and vice versa. Produces one new Hypothesis.

   **header_length_scan** — Produces multiple candidate Hypotheses by trying adjusted header lengths. For the base `header_size`, tries `header_size + k` for `k ∈ {1, 2, 4, 8, 16, 32, 64, 128}` and `header_size − k` for `k ∈ {1, 2, 4}`, in that order, skipping values outside `[0, total_file_size)`. Each adjusted header length is a separate candidate.

   **row_padding_variants** — Produces three candidate Hypotheses with `row_padding ∈ {1, 2, 4}` bytes respectively, all other parameters unchanged.

   **rle_pcx** — Sets `encoding = "rle_pcx"` on the Hypothesis, leaving all other parameters unchanged. Produces one new Hypothesis.

4. FOR each candidate Hypothesis produced by a strategy sequence, THE Engine SHALL apply the closure gate immediately. IF a candidate passes, THE Engine SHALL return a `VerifiedHypothesis` with `revision_path` set to the ordered list of strategy names applied and halt all further search.

5. THE Engine SHALL deduplicate: if a candidate Hypothesis has identical parameters (`width`, `height`, `bit_depth`, `header_size`, `row_padding`, `encoding`) to any previously closure-checked Hypothesis, it SHALL be skipped without re-checking.

6. THE Engine SHALL enforce a hard cap of 10,000 total closure checks shared across the Revision Phase and Generic Search. IF the cap is reached before a passing Hypothesis is found, THE Engine SHALL return a `FailureReport` with the rejection list accumulated so far plus a final entry with `reason = "search_cap_exceeded"`. The check count and the wall-clock deadline (Requirement 1 criterion 7) are independent termination conditions; whichever triggers first wins.

7. WHEN a strategy combination produces multiple candidates (header_length_scan, row_padding_variants), each candidate is closure-checked in the order the strategy defines before moving to the next candidate of that strategy.

---

### Requirement 4: Generic Search

**User Story:** As a developer verifying the Engine's core capability, I want the Engine to find a closing hypothesis for a file that matches no registered probe, using only generic structural search, so that NECROPSY can handle formats beyond its known probe set.

#### Acceptance Criteria

1. WHEN all Probes have been attempted and none generated a Hypothesis (i.e., every probe was a signature mismatch or file-too-short skip), THE Engine SHALL enter the Generic Search phase.

2. THE Generic Search SHALL enumerate candidate header lengths in order: every multiple of 4 from 4 to 256 inclusive, plus every power of 2 from 4 to 256 inclusive, deduplicated and sorted ascending. For each candidate header length `h`, the data region is `data[h:]`.

3. FOR each candidate header length, THE Engine SHALL try reading `width` and `height` using formats `<H`, `>H`, `<I`, `>I`, `<i`, `>i` at all valid byte offsets within the header, and `bit_depth` as `B` at all valid byte offsets within the header. Format size is 2 bytes for `H` formats and 4 bytes for `I`/`i` formats; a field offset is valid if `offset + format_size ≤ h`.

4. THE Engine SHALL skip any combination where `width ≤ 0`, `height ≤ 0`, `bit_depth ∉ {1, 4, 8, 16, 24, 32}`, `width_offset == height_offset`, or `header_size + row_stride × height > total_file_size`.

5. FOR each non-skipped combination, THE Engine SHALL first apply the closure gate with `encoding = "none"`. IF that fails, THE Engine SHALL also try `encoding = "rle_pcx"`. IF either passes, THE Engine SHALL return a `VerifiedHypothesis` with `probe_name = "generic"`, `revision_path = []`, and the winning combination's field offsets, formats, and values as `FieldRecord` entries.

6. THE `VerifiedHypothesis` for a generic-search result SHALL record: the winning `header_size`, `width_offset`, `width_format`, `height_offset`, `height_format`, and `bit_depth_offset` as named fields, so the search axes that resolved the file are observable in the result.

7. WHEN the Generic Search exhausts all combinations without finding a closing Hypothesis, THE Engine SHALL return a `FailureReport`; it SHALL NOT return a guess.

8. THE Generic Search is not guaranteed to be exhaustive: the search space at header length 256 alone exceeds 500 million combinations before skip guards are applied, so the wall-clock deadline and the shared 10,000-check cap (Requirement 3 criterion 6) will typically terminate the search before it is complete. THE Engine SHALL NOT claim or imply that a `FailureReport` from Generic Search means the file has no closing hypothesis; the report merely records what was tried within the allotted budget.

---

### Requirement 5: Failure Report

**User Story:** As a developer debugging an unresolvable file, I want the Engine to return a complete account of every Hypothesis tried and why each was rejected, so that I can diagnose the failure without re-running the Engine.

#### Acceptance Criteria

1. WHEN all Probes, Revision Strategies, and Generic Search have been exhausted without finding a closing Hypothesis, THE Engine SHALL return a `FailureReport`.

2. THE `FailureReport` SHALL contain a list of `RejectionEntry` records. Each record SHALL include:
   - The Hypothesis parameters (`width`, `height`, `bit_depth`, `header_size`, `row_padding`, `encoding`).
   - The struct format string and byte offset of every field extracted.
   - The closure failure reason: `arithmetic_mismatch` (with discrepancy value), `decoder_overrun`, `decoder_underrun`, `field_out_of_bounds`, `search_cap_exceeded`, or `deadline_exceeded`.
   - The name of the Probe or the ordered strategy sequence (e.g., `["inclusive_bounds", "rle_pcx"]`) that produced the Hypothesis.

3. IF the input byte sequence is fewer than 3 bytes, THEN THE Engine SHALL return a `FailureReport` whose `RejectionEntry` list contains exactly one entry with `reason = "input_too_short"` and SHALL NOT attempt any Probe or Search.

4. THE `FailureReport` SHALL record entries in the order: probe rejections first (in probe order), then revision-phase rejections (in breadth-first depth order), then generic-search rejections.

---

### Requirement 6: Never-Raise Contract

**User Story:** As a developer running automated tests against arbitrary byte sequences, I want the Engine to handle all inputs without raising an exception, so that NECROPSY does not crash on corrupted or adversarial files.

#### Acceptance Criteria

1. IF any exception propagates to the Engine's top-level entry point during processing, THEN THE Engine SHALL catch it and return a `FailureReport` containing a single `RejectionEntry` whose `reason` field is the exception class name and message; all Hypothesis parameter fields in that entry SHALL be absent.

2. WHEN given a zero-length byte sequence, THE Engine SHALL return a `FailureReport`; it SHALL NOT raise.

3. WHEN given a byte sequence of arbitrary length and content, THE Engine SHALL return either a `VerifiedHypothesis` or a `FailureReport`; it SHALL NOT raise.

4. THE Engine SHALL be tested with a Hypothesis property test using the `hypothesis` library that generates arbitrary `bytes` inputs up to 65,536 bytes in length and asserts the Engine returns a `HypothesisResult` without raising.

5. THE Engine SHALL be tested with a Hypothesis property test using the `hypothesis` library that generates arbitrary `bytes` inputs up to 65,536 bytes in length, runs the Engine with `deadline_seconds=5.0`, and asserts the Engine returns a `HypothesisResult` within 5 seconds without raising.

---

### Requirement 7: Test Corpus Verification

**User Story:** As a developer validating the Engine against known ground truth, I want the Engine to correctly identify all eight corpus files with their exact revision paths, so that each revision strategy and search path has at least one verifiable acceptance test.

#### Acceptance Criteria

1. WHEN given the bytes of `spike/samples/mystery_a` (PBM P4, 4×4, 1 bpp, 11 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=4`, `height=4`, `bit_depth=1`, `header_size=7`, `row_stride=1`, `revision_path=[]`.

2. WHEN given the bytes of `spike/samples/mystery_b` (PCX RLE, 8×8, 8 bpp, 955 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=8`, `height=8`, `bit_depth=8`, `header_size=128`, `encoding="rle_pcx"`, `revision_path=["inclusive_bounds","rle_pcx"]`.

3. WHEN given the bytes of `spike/samples/mystery_c` (TGA uncompressed, 16×16, 24 bpp, 786 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=16`, `height=16`, `bit_depth=24`, `header_size=18`, `row_stride=48`, `revision_path=[]`.

4. WHEN given the bytes of `spike/samples/mystery_d` (DIB body, 8×8, 8 bpp, 104 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=8`, `height=8`, `bit_depth=8`, `header_size=40`, `probe_name="generic"`, and `FieldRecord` entries recording `width_offset=0x04`, `width_format="<i"`, `height_offset=0x08`, `height_format="<i"`, `bit_depth_offset=0x0E`.

5. WHEN given the bytes of `spike/samples/mystery_e` (TIFF big-endian "MM", 8×8, 8 bpp, 150 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=8`, `height=8`, `bit_depth=8`, `header_size=86`, `revision_path=["endianness_flip"]`.

6. WHEN given the bytes of `spike/samples/mystery_f` (raw 32-bit dims, 12×10, 8 bpp, 132 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=12`, `height=10`, `bit_depth=8`, `header_size=12`, `probe_name="generic"`, and `FieldRecord` entries recording `width_offset=0x00`, `width_format="<I"`, `height_offset=0x04`, `height_format="<I"`, `bit_depth_offset=0x08`.

7. WHEN given the bytes of `spike/samples/mystery_g` (raw unusual header, 8×8, 24 bpp, 212 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=8`, `height=8`, `bit_depth=24`, `header_size=20`, `probe_name="generic"`, and `FieldRecord` entries recording `width_offset=0x04`, `width_format="<H"`, `height_offset=0x06`, `height_format="<H"`, `bit_depth_offset=0x08`.

8. WHEN given the bytes of `spike/samples/mystery_h` (PCX padded rows, 6×6, 8 bpp, 176 bytes), THE Engine SHALL return a `VerifiedHypothesis` with `width=6`, `height=6`, `bit_depth=8`, `header_size=128`, `row_stride=8`, `revision_path=["inclusive_bounds","row_padding_variants"]`.

9. FOR ALL eight corpus files, THE Engine SHALL return a `VerifiedHypothesis`, not a `FailureReport`.

---

### Requirement 8: Round-Trip Structural Integrity

**User Story:** As a developer verifying the Engine's field extraction, I want the VerifiedHypothesis to contain enough information to reconstruct the field extraction exactly, so that the extraction can be independently replicated without re-running the Engine.

#### Acceptance Criteria

1. THE Engine SHALL record each extracted field as a `FieldRecord` containing: field name (string), byte offset (int), struct format string (string), and extracted value stored as the tuple returned directly by `struct.unpack_from` without unpacking.

2. THE Engine SHALL ensure that for every `FieldRecord` in a `VerifiedHypothesis`, calling `struct.unpack_from(record.format, original_bytes, record.offset)` produces a tuple equal to `record.extracted_value`.

3. WHEN the Pretty_Printer is given a `VerifiedHypothesis`, THE Pretty_Printer SHALL render a human-readable table with columns in the order: offset (hex), field name, struct format, extracted value; followed by a closure line in the form `{header_size} + {row_stride × height} = {total_file_size}` with all three values as decimal integers; followed by `revision_path: {revision_path}`.

4. WHEN the Pretty_Printer is given a `FailureReport`, THE Pretty_Printer SHALL render a numbered list of rejection entries in the order they appear in the report, each entry showing the strategy sequence and the closure failure reason.
