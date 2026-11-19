# Implementation Plan: Structure-Inference Engine

## Overview

Build the Structure-Inference Engine as a pure-Python package under `necropsy/engine/`, with no network calls and no GPU. The engine takes arbitrary bytes and returns a `VerifiedHypothesis` or a `FailureReport`. It never raises. Tasks run bottom-up: types, closure gate, probes, strategies, generic search, engine, pretty printer, corpus tests, property tests.

Rules that apply to every task:

- Byte offsets and struct formats are copied verbatim from requirements.md (Requirement 2.1 and Requirement 4.3). Do not change them.
- Parsers and the engine entry point never raise on malformed input. They return a structured error.
- Every parser gets a Hypothesis property test asserting it never raises on arbitrary bytes.
- Build only what a task asks for. Add no formats, variants or options.
- Shell is Windows PowerShell 5.1. Use `;` as the statement separator, never `&&`. Run tests with `python -m pytest tests/<file> -q`.
- All tests, including property tests, are required. None are marked optional.

## Open Spec Conflicts (resolve before starting the affected tasks)

requirements.md and design.md were checked against `spike/samples/`. Two Requirement 7 expectations cannot be met by the probe behaviour the spec describes. Tasks 3.1, 3.4, 8.1 and 8.2 implement the spec literally. If a corpus test fails for one of the reasons below, stop and report it. Do not bend unrelated code to make the test pass.

1. **mystery_b (Requirement 7.2).** Byte 2 of mystery_b is `0x01`, so Requirement 2.1 selects `encoding = "rle_pcx"` on the initial PCX hypothesis. The initial hypothesis is `7x7` (raw `xmax`, `ymax`). `inclusive_bounds` then gives `8x8` with `rle_pcx`, which closes at depth 1 with `revision_path = ["inclusive_bounds"]`. Requirement 7.2 expects `["inclusive_bounds","rle_pcx"]`. The two cannot both hold. To get the expected path, the probe would have to start with `encoding = "none"` for byte 2 `0x01` as well, which is what the earlier design draft did.
2. **mystery_e (Requirement 7.5).** The bytes are `4d 4d 00 2a 00 00 00 08 ...`. Reading `ifd_offset` naively as `<I` at 0x04 gives `0x08000000`, which is outside the file. Requirement 2.1 says to record `field_out_of_bounds` and continue, so no seed exists and `endianness_flip` never runs. Even with a seed, the IFD tags cannot be found by walking the IFD in little-endian. Reaching `["endianness_flip"]` needs a decision on how the TIFF probe builds a seed for an `MM` file.

Also confirm one small addition. Requirement 2.1 says to "record a RejectionEntry" when a probe's extra conditions fail (PCX `xmax < xmin`, `ymax < ymin` or `bytes_per_line == 0`; TGA or PBM `width <= 0` or `height <= 0`), but gives no reason string. Task 6.1 uses `probe_precondition_failed`. This is not in the Requirement 5.2 reason list.

## Tasks

- [ ] 1. Package scaffold and types
  - [ ] 1.1 Create the package skeleton
    - Create `necropsy/__init__.py` (empty), `necropsy/engine/__init__.py` (empty for now), `tests/__init__.py` (empty)
    - Create only these files. Each later task creates its own module.
    - _Requirements: 6.3_

  - [ ] 1.2 Implement `necropsy/engine/types.py`
    - `FieldRecord(name: str, offset: int, fmt: str, value: tuple)`. `value` is the tuple returned by `struct.unpack_from`, never unwrapped.
    - `Hypothesis(width, height, bit_depth, header_size, row_padding=0, encoding="none", fields=[], probe_name="", revision_path=[], xmin=None, ymin=None, xmax=None, ymax=None)`. Use `field(default_factory=list)` for the list defaults.
    - `RejectionEntry(hypothesis: Hypothesis | None, reason: str, discrepancy: int | None, source: str)`
    - `VerifiedHypothesis(hypothesis, row_stride, expected_decoded_bytes, total_file_size, width_offset=None, width_format=None, height_offset=None, height_format=None, bit_depth_offset=None)`
    - `FailureReport(rejections: list[RejectionEntry], total_checks: int)`
    - `HypothesisResult = VerifiedHypothesis | FailureReport`
    - `ProbeResult = Hypothesis | RejectionEntry | None`. `None` means signature mismatch or file too short (silent skip). `RejectionEntry` is for a signature match that cannot build a hypothesis, such as TIFF `field_out_of_bounds`.
    - `hypothesis_key(h) -> tuple` returning `(width, height, bit_depth, header_size, row_padding, encoding)`
    - No business logic in this module.
    - _Requirements: 1.3, 1.5, 3.5, 5.2, 8.1_

- [ ] 2. Closure gate
  - [ ] 2.1 Implement `compute_row_stride` and the typed RLE decoder in `necropsy/engine/closure.py`
    - `compute_row_stride(width, bit_depth, row_padding) -> int`: `width * bit_depth // 8 + row_padding` when `bit_depth >= 8`, else `ceil(width * bit_depth / 8) + row_padding`. Use integer arithmetic (`-(-n // 8)`) so no float rounding applies.
    - `RleResult` dataclass: `status: str` (one of `"ok"`, `"overrun"`, `"underrun"`) and `data: bytes | None`. `data` is set only when `status == "ok"`.
    - `rle_pcx_decode(data, start, max_output_bytes) -> RleResult`. Decode from `data[start:]`:
      - A byte `>= 0xC0` is a run marker. The count is `b & 0x3F` and the value is the next byte.
      - Any other byte is a literal.
      - Abort inside the loop, before extending the output, the moment a run or literal would push the output past `max_output_bytes`. Return `status="overrun"`. Never allocate beyond `max_output_bytes`.
      - If the input ends before `max_output_bytes` bytes are produced, including a run marker with no value byte, return `status="underrun"`.
      - Return `status="ok"` only when the output length equals `max_output_bytes` exactly.
    - Handle `start < 0`, `start > len(data)` and `max_output_bytes < 0` by returning a typed result. Never raise.
    - This replaces the `bytes | None` return in design.md so `check_closure` needs only one decode pass.
    - _Requirements: 1.1, 1.2, 1.6_

  - [ ] 2.2 Implement `check_closure` in `necropsy/engine/closure.py`
    - `check_closure(h: Hypothesis, data: bytes) -> tuple[bool, str, int | None]`
    - `encoding == "none"`: pass when `h.header_size + row_stride * h.height == len(data)`. Otherwise return `(False, "arithmetic_mismatch", len(data) - (h.header_size + row_stride * h.height))`.
    - `encoding == "rle_pcx"`: call `rle_pcx_decode(data, h.header_size, row_stride * h.height)` once. Map `ok` to `(True, "", None)`, `overrun` to `(False, "decoder_overrun", None)` and `underrun` to `(False, "decoder_underrun", None)`.
    - Return `(False, "arithmetic_mismatch", None)` for any other encoding value, and for negative `header_size`, `width` or `height`. Never raise.
    - The gate is binary. No scoring.
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 2.3 Write unit tests in `tests/test_closure.py`
    - `compute_row_stride`: 24 bpp (width 16 gives 48), 8 bpp with padding, 1 bpp (width 4 gives 1, width 9 gives 2).
    - `rle_pcx_decode`: valid literal and run mix returns `ok`. A run exceeding `max_output_bytes` mid-stream returns `overrun`. Truncated input and a trailing run marker with no value byte return `underrun`. A large run count with a small `max_output_bytes` aborts without producing more than `max_output_bytes` bytes.
    - `check_closure`: `arithmetic_mismatch` with the correct signed discrepancy, a correct `none` match, `decoder_overrun`, `decoder_underrun`, and a successful `rle_pcx` match.
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

- [ ] 3. Probes
  - [ ] 3.1 Implement the PCX probe in `necropsy/engine/probes.py`
    - `probe_pcx(data: bytes) -> ProbeResult`. Return `None` unless `len(data) >= 128`, `data[0] == 0x0A` and `data[2] in (0, 1)`.
    - Read with `struct.unpack_from` and store each as a `FieldRecord`: `xmin` at `0x04` `<H`, `ymin` at `0x06` `<H`, `xmax` at `0x08` `<H`, `ymax` at `0x0A` `<H`, `bit_depth` at `0x03` `B`, `planes` at `0x41` `B`, `bytes_per_line` at `0x42` `<H`.
    - Build the hypothesis with `width = xmax`, `height = ymax` (raw values, no arithmetic), `bit_depth` from the field, `header_size = 128`, `encoding = "none"` when `data[2] == 0x00` and `"rle_pcx"` when `data[2] == 0x01`, `probe_name = "PCX"`, and `xmin/ymin/xmax/ymax` populated.
    - Expose `pcx_preconditions_ok(h) -> bool`, true when `xmax >= xmin`, `ymax >= ymin` and `bytes_per_line > 0`.
    - See Open Spec Conflict 1 for the effect on mystery_b.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.2 Implement the TGA probe in `necropsy/engine/probes.py`
    - `probe_tga(data) -> ProbeResult`. Return `None` if `len(data) < 3`, if `data[2]` is not in `{1, 2, 3, 9, 10, 11}`, or if `len(data) < 18 + data[0]`.
    - Fields as `FieldRecord`: `id_length` at `0x00` `B`, `image_type` at `0x02` `B`, `width` at `0x0C` `<H`, `height` at `0x0E` `<H`, `bit_depth` at `0x10` `B`. Check length before every read.
    - Hypothesis: `header_size = 18 + id_length`, `encoding = "none"`, `probe_name = "TGA"`.
    - Expose `tga_preconditions_ok(h) -> bool`, true when `width > 0` and `height > 0`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.3 Implement the PBM probe in `necropsy/engine/probes.py`
    - `probe_pbm(data) -> ProbeResult`. Return `None` unless `len(data) >= 7` and `data[0:3] == b"P4\n"`.
    - Parse the header after byte 3 line by line. Skip lines starting with `#`. Take the first non-comment line, split on whitespace, and read `width` and `height` as ASCII decimal integers. If the digits are missing or malformed, return `None`. Never raise.
    - `header_size` is the offset of the first byte after the newline ending the dimensions line. `bit_depth = 1`, `encoding = "none"`, `probe_name = "PBM"`.
    - Row stride comes from `compute_row_stride(width, 1, 0)`, which equals `ceil(width / 8)`.
    - Record only fields that `struct.unpack_from` can reproduce (Requirement 8.2). That is the magic bytes as a `FieldRecord` named `magic` with `fmt = "3s"` at `0x00`. The ASCII width and height cannot be reproduced by `struct.unpack_from`, so they are not `FieldRecord`s. Say so in a code comment.
    - Expose `pbm_preconditions_ok(h) -> bool`, true when `width > 0` and `height > 0`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.4 Implement the TIFF probe in `necropsy/engine/probes.py`
    - `probe_tiff(data) -> ProbeResult`. Return `None` if `len(data) < 8`, if `data[0:2]` is not `b"II"` or `b"MM"`, or if the `uint16` at `0x02` read in the declared byte order (`<H` for `II`, `>H` for `MM`) is not 42.
    - Read `ifd_offset` at `0x04` as `<I`. This is naive little-endian for both byte orders.
    - If `ifd_offset + 2 > len(data)`, return `RejectionEntry(hypothesis=None, reason="field_out_of_bounds", discrepancy=None, source="TIFF")`.
    - Read the entry count at `ifd_offset` as `<H`. Walk the 12-byte entries. For tags 256, 257, 258, 273 and 279, read the value as `<H` or `<I` depending on the entry type field (3 is SHORT and 4 is LONG, both naive little-endian). If any entry or value offset is outside `[0, len(data))`, return the `field_out_of_bounds` `RejectionEntry`.
    - Name the fields `ifd_offset`, `width`, `height`, `bit_depth`, `strip_offset` and `strip_byte_count`. Each is a `FieldRecord` with its real offset and format. If a tag is missing, return `RejectionEntry` with `field_out_of_bounds`.
    - Hypothesis: `header_size = strip_offset`, `encoding = "none"`, `probe_name = "TIFF"`. The probe's extra closure condition is `strip_offset + strip_byte_count == len(data)`. Expose `tiff_preconditions_ok(h, data) -> bool`.
    - See Open Spec Conflict 2 for the effect on mystery_e.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.5 Write unit tests in `tests/test_probes.py`
    - For each probe: the matching corpus file returns a `Hypothesis` (PCX: mystery_b and mystery_h; TGA: mystery_c; PBM: mystery_a; TIFF: see Open Spec Conflict 2 for mystery_e), a non-matching signature returns `None`, and a file shorter than the probe minimum returns `None`.
    - PCX: assert `data[2] == 0` gives `encoding == "none"`, `data[2] == 1` gives `"rle_pcx"`, `data[2] == 2` returns `None`, and the field offsets and formats equal Requirement 2.1 exactly. Assert `xmin/ymin/xmax/ymax` are populated.
    - TGA: assert `mystery_a` (`P4\n...`, `data[2] == 0x0A`) returns `None` because it is shorter than `18 + data[0]`.
    - TIFF: a crafted `II` file with an out-of-range `ifd_offset` returns a `RejectionEntry` with `reason == "field_out_of_bounds"`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.6 Write a never-raises property test for each probe in `tests/test_probes.py`
    - **Property: each probe never raises on arbitrary bytes**
    - **Validates: Requirements 6.3**
    - One `@given(st.binary(max_size=65536))` test per probe (`probe_pcx`, `probe_tga`, `probe_pbm`, `probe_tiff`) with `@settings(max_examples=100)`. Assert the return value is a `Hypothesis`, a `RejectionEntry` or `None`.
    - Add a second generator that prefixes each probe's valid signature to arbitrary bytes so the post-signature code paths run.
    - Tag: `Feature: structure-inference-engine, Probe never raises`

- [ ] 4. Revision strategies
  - [ ] 4.1 Implement `apply_inclusive_bounds`, `apply_row_padding_variants` and `apply_rle_pcx` in `necropsy/engine/strategies.py`
    - Signature for all strategies: `apply_xxx(h: Hypothesis, data: bytes) -> list[Hypothesis]`. Use `dataclasses.replace` and copy `fields` and `revision_path` lists so candidates share no mutable state.
    - `apply_inclusive_bounds`: return `[]` unless `xmin`, `ymin`, `xmax` and `ymax` are all not `None`. Otherwise one candidate with `width = xmax - xmin + 1`, `height = ymax - ymin + 1`, all else unchanged, `revision_path + ["inclusive_bounds"]`.
    - `apply_row_padding_variants`: three candidates with `row_padding` of 1, 2 and 4 in that order, `revision_path + ["row_padding_variants"]`.
    - `apply_rle_pcx`: one candidate with `encoding = "rle_pcx"`, `revision_path + ["rle_pcx"]`.
    - _Requirements: 3.3_

  - [ ] 4.2 Implement `apply_endianness_flip` in `necropsy/engine/strategies.py`
    - Iterate `h.fields`. Flip the prefix `<` to `>` and `>` to `<` for every multi-byte field (`H`, `I`, `i`). Leave `B` and `b` unchanged.
    - Re-read each flipped field with `struct.unpack_from(new_fmt, data, fr.offset)` and produce a new `FieldRecord`. Catch `struct.error` and return `[]`. Never raise.
    - Rebuild `width`, `height` and `bit_depth` from the flipped field values with those names. Set `header_size` from the flipped `strip_offset` when that field exists. Leave other parameters unchanged.
    - Return `[]` when `h.fields` has no multi-byte field. Otherwise return one candidate with `revision_path + ["endianness_flip"]`.
    - _Requirements: 3.3_

  - [ ] 4.3 Implement `apply_header_length_scan` and the `STRATEGIES` list in `necropsy/engine/strategies.py`
    - `apply_header_length_scan`: candidates for `header_size + k` with `k` in `(1, 2, 4, 8, 16, 32, 64, 128)`, then `header_size - k` with `k` in `(1, 2, 4)`, in that order. Skip any value outside `[0, len(data))`. Each is a separate candidate with `revision_path + ["header_length_scan"]`.
    - `STRATEGIES = [("inclusive_bounds", apply_inclusive_bounds), ("endianness_flip", apply_endianness_flip), ("header_length_scan", apply_header_length_scan), ("row_padding_variants", apply_row_padding_variants), ("rle_pcx", apply_rle_pcx)]`. Keep this order. It fixes the BFS order and therefore which `revision_path` is found first.
    - _Requirements: 3.3, 3.7_

  - [ ] 4.4 Write unit tests in `tests/test_strategies.py`
    - `apply_inclusive_bounds`: a PCX hypothesis with `xmin=0, xmax=7` gives `width == 8`. A hypothesis without bounds gives `[]`.
    - `apply_endianness_flip`: a hand-built hypothesis with `<H` fields over a big-endian buffer gives the big-endian values and `>H` formats. A hypothesis with only `B` fields gives `[]`. A flip whose re-read would run past the buffer gives `[]` and does not raise.
    - `apply_header_length_scan`: order is `+1, +2, +4, +8, +16, +32, +64, +128, -1, -2, -4`. Values outside `[0, len(data))` are skipped.
    - `apply_row_padding_variants`: exactly three candidates with padding `[1, 2, 4]`.
    - `apply_rle_pcx`: sets the encoding and appends the name.
    - Every candidate's `revision_path` extends the input's path and does not mutate the input.
    - _Requirements: 3.3, 3.7_

  - [ ] 4.5 Write a never-raises property test in `tests/test_strategies.py`
    - **Property: each strategy never raises on arbitrary hypotheses and bytes**
    - **Validates: Requirements 6.3**
    - Generate arbitrary `bytes` and a `Hypothesis` with arbitrary ints, arbitrary `FieldRecord` offsets, and formats drawn from `<H >H <I >I <i >i B`. Run all five strategies with `@settings(max_examples=100)`. Assert each returns a `list` of `Hypothesis`.
    - Tag: `Feature: structure-inference-engine, Strategy never raises`

- [ ] 5. Generic search
  - [ ] 5.1 Implement `generic_search` in `necropsy/engine/generic.py`
    - Signature: `generic_search(data, over_limit, tick, on_reject) -> VerifiedHypothesis | None`. These three callables are supplied by the Engine so one deadline and one 10,000 budget cover both the revision BFS and generic search. This module owns no clock and no counter.
      - `over_limit() -> str | None`: returns `"deadline_exceeded"`, `"search_cap_exceeded"` or `None`. Call it before every closure check. When it returns a reason, return `None` immediately.
      - `tick() -> None`: increments the Engine's shared check counter. Call it once per closure check, immediately before `check_closure`.
      - `on_reject(h, reason, discrepancy) -> None`: lets the Engine record a `RejectionEntry` with source `"generic"`.
    - `HEADER_LENGTHS = sorted(set(range(4, 257, 4)) | {4, 8, 16, 32, 64, 128, 256})`. Skip lengths `>= len(data)`.
    - Formats and sizes: `<H >H` = 2 bytes, `<I >I <i >i` = 4 bytes. A field offset is valid when `offset + size <= header_length`. `bit_depth` is `B` at any offset below the header length.
    - Enumeration order: header length, then width format and offset, then height format and offset, then `bit_depth` offset. This order decides which axes win, so do not reorder it.
    - Skip when `width <= 0`, `height <= 0`, `bit_depth` not in `{1, 4, 8, 16, 24, 32}`, `width_offset == height_offset`, or `header_size + row_stride * height > len(data)` (with `row_padding = 0`). Skipped combinations do not call `tick`.
    - For each remaining combination, check `encoding = "none"` first, then `"rle_pcx"` only if the first failed. Each is its own `over_limit`, `tick` and `check_closure` sequence.
    - On pass, return `VerifiedHypothesis` with `probe_name = "generic"`, `revision_path = []`, `row_padding = 0`, and `FieldRecord`s named `width`, `height` and `bit_depth` with their real offsets and formats. Set the top-level `width_offset`, `width_format`, `height_offset`, `height_format` and `bit_depth_offset`. Set `row_stride`, `expected_decoded_bytes` and `total_file_size`.
    - Return `None` on exhaustion or budget stop. The engine decides what that means. A `None` is never read as proof that no closing hypothesis exists.
    - Never raise. Guard every `struct.unpack_from`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ] 5.2 Write unit tests in `tests/test_generic.py`
    - Use a test limiter: `over_limit` returning `None`, `tick` counting, `on_reject` appending.
    - mystery_d, mystery_f and mystery_g each resolve with the `header_size`, `width_offset`, `width_format`, `height_offset`, `height_format` and `bit_depth_offset` from Requirements 7.4, 7.6 and 7.7. If an earlier enumeration order finds a different closing combination, stop and report it. Do not reorder to fit.
    - A buffer with no closing hypothesis returns `None`.
    - `over_limit` returning `"search_cap_exceeded"` after N ticks stops the search with at most N checks.
    - `HEADER_LENGTHS` starts `[4, 8, 12, 16]`, ends at 256, has no duplicates and is ascending.
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 7.4, 7.6, 7.7_

  - [ ] 5.3 Write a never-raises property test in `tests/test_generic.py`
    - **Property: `generic_search` never raises on arbitrary bytes**
    - **Validates: Requirements 6.3, 3.6**
    - `@given(st.binary(max_size=65536))` with `@settings(max_examples=100, deadline=None)`. Use a limiter that stops at 10,000 ticks. Assert the result is `VerifiedHypothesis` or `None` and the tick count never exceeds 10,000.
    - Tag: `Feature: structure-inference-engine, Generic search never raises`

- [ ] 6. Engine
  - [ ] 6.1 Implement `Engine`, the shared limiter and the probe phase in `necropsy/engine/engine.py`
    - `Engine(deadline_seconds: float = 5.0)` with `run(data) -> HypothesisResult`.
    - Per-run state, reset at the start of every `run()`: `_start = time.monotonic()`, `_check_count = 0`, `_rejections = []`, `_terminated = None`, `_seen = set()`.
    - `_over_limit() -> str | None`: `"deadline_exceeded"` when `time.monotonic() - _start >= deadline_seconds`, else `"search_cap_exceeded"` when `_check_count >= 10_000`, else `None`. Deadline is tested first. Call it before every closure check.
    - `_tick()` increments `_check_count`. `_check(h, source)` runs `_over_limit`, `_tick`, `check_closure`, and on failure records a `RejectionEntry` (`hypothesis`, `reason`, `discrepancy`, `source`).
    - `len(data) < 3`: return `FailureReport` with exactly one `RejectionEntry` having `reason = "input_too_short"` and `hypothesis=None`. Run no probe.
    - Probe phase: run `probe_pcx`, `probe_tga`, `probe_pbm`, `probe_tiff` in that order. `None` is skipped silently. A `RejectionEntry` is appended to the rejection list. A `Hypothesis` first goes through its probe's `*_preconditions_ok`. A failing precondition records `RejectionEntry(reason="probe_precondition_failed")` and keeps the hypothesis as a seed. Otherwise it goes through `_check`, and a pass returns a `VerifiedHypothesis` immediately. A failed hypothesis is added to `seeds` and its key to `_seen`.
    - A `VerifiedHypothesis` has `row_stride = compute_row_stride(...)`, `expected_decoded_bytes = row_stride * height`, `total_file_size = len(data)`. Add a helper `_make_verified(h, data)`.
    - Probe closure checks count toward `total_checks` and the cap.
    - If `_over_limit` fires, return a `FailureReport` with the accumulated rejections plus a final `RejectionEntry` whose `reason` is `"deadline_exceeded"` or `"search_cap_exceeded"`.
    - _Requirements: 1.5, 1.7, 2.1, 2.2, 2.3, 2.4, 3.6, 5.2, 5.3, 5.4_

  - [ ] 6.2 Implement the revision BFS in `necropsy/engine/engine.py`
    - Enter only when `seeds` is non-empty (at least one probe produced a rejected hypothesis).
    - `frontier = seeds`. For depth 1 to 3: for each `base` in `frontier` in order, for each strategy in `STRATEGIES` order, for each candidate in the strategy's list order, skip it if `hypothesis_key` is in `_seen`, otherwise add the key. Then run `_check(candidate, source=str(candidate.revision_path))`. A pass returns `_make_verified` with the candidate's `revision_path` and ends the search. A fail appends to `next_frontier`. Set `frontier = next_frontier` after each depth.
    - Every candidate of a multi-candidate strategy is checked in the strategy's order before the next strategy.
    - A limit stop returns the termination `FailureReport` from 6.1. Exhaustion at depth 3 returns the `FailureReport` with all rejections. Generic search is not entered.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.4_

  - [ ] 6.3 Implement generic dispatch, failure assembly and the never-raise wrapper in `necropsy/engine/engine.py`
    - Enter generic search only when no probe returned a `Hypothesis` or `RejectionEntry` (every probe was a silent skip). Pass `self._over_limit`, `self._tick` and an `on_reject` callback that appends `RejectionEntry(source="generic")` to the shared list. This is the same limiter object the BFS uses.
    - A `VerifiedHypothesis` from `generic_search` is returned as is. A `None` result leads to a `FailureReport`. If `_over_limit()` is non-`None` at that point, add the final `deadline_exceeded` or `search_cap_exceeded` entry.
    - `FailureReport.total_checks = _check_count`. Rejection order is probe, revision, generic.
    - `run()` wraps `_run_inner()` in `try/except Exception as exc`. Return `FailureReport(rejections=[RejectionEntry(hypothesis=None, reason=f"{type(exc).__name__}: {exc}", discrepancy=None, source="uncaught_exception")], total_checks=0)`.
    - Export `Engine` and the types from `necropsy/engine/__init__.py`.
    - _Requirements: 3.6, 4.1, 4.7, 4.8, 5.1, 5.2, 5.4, 6.1, 6.2, 6.3_

  - [ ] 6.4 Write unit tests in `tests/test_engine.py`
    - `b""` and a 2-byte input return a `FailureReport` with one entry, `reason == "input_too_short"`, `hypothesis is None`.
    - A probe monkeypatched to raise returns a `FailureReport` with a single entry whose `reason` starts with the exception class name and whose `hypothesis` is `None`.
    - `Engine(deadline_seconds=0.0)` on a corpus file returns a `FailureReport` whose last entry is `deadline_exceeded`.
    - With `_check_count` preset to 10,000, a run returns a final `search_cap_exceeded` entry.
    - Dedup: a candidate with an already-seen key is not re-checked. Count `check_closure` calls with a spy.
    - The shared limiter is the same object for the BFS and generic search: a spy confirms `generic_search` receives the engine's `_over_limit` and `_tick`.
    - Rejection order is probe entries, then revision entries, then generic entries.
    - _Requirements: 1.7, 3.5, 3.6, 5.3, 5.4, 6.1, 6.2_

- [ ] 7. Pretty printer
  - [ ] 7.1 Implement `PrettyPrinter` in `necropsy/engine/pretty.py`
    - `PrettyPrinter.render(result: HypothesisResult) -> str`, a pure function that does not mutate the result.
    - Verified output: a title line, a header row with columns in the order offset (hex), field name, struct format, extracted value, then one row per `FieldRecord` with the offset as `0x{offset:04X}`. Then a blank line, then the closure line `Closure: {header_size} + {row_stride * height} = {total_file_size}` with all three as decimal integers, then `revision_path: {revision_path}`.
    - Failure output: a title line with entry and check counts, then a numbered list in report order. Each line shows the `source` and the `reason`, with `(discrepancy=N)` appended when the discrepancy is not `None`.
    - Handle `RejectionEntry.hypothesis is None` without raising.
    - Export `PrettyPrinter` from `necropsy/engine/__init__.py`.
    - _Requirements: 8.3, 8.4_

  - [ ] 7.2 Write unit tests in `tests/test_pretty.py`
    - A minimal `VerifiedHypothesis`: assert the column order, the hex offset format, a line ending in `{header_size} + {row_stride * height} = {total_file_size}` with decimal values, and a `revision_path: [...]` line.
    - A minimal `FailureReport`: assert 1-based numbering, report order, and the `source` and `reason` on each line.
    - An entry with `hypothesis=None` renders without raising.
    - Rendering twice gives the same string and leaves the result unchanged.
    - _Requirements: 8.3, 8.4_

- [ ] 8. Corpus integration tests
  - [ ] 8.1 Write corpus tests for mystery_a through mystery_d in `tests/test_engine.py`
    - Read files from `spike/samples/` relative to the repo root. Run `Engine().run(data)` and assert `isinstance(result, VerifiedHypothesis)`.
    - mystery_a: `width=4`, `height=4`, `bit_depth=1`, `header_size=7`, `row_stride=1`, `revision_path == []`.
    - mystery_b: `width=8`, `height=8`, `bit_depth=8`, `header_size=128`, `encoding="rle_pcx"`, `revision_path == ["inclusive_bounds","rle_pcx"]`. See Open Spec Conflict 1. If this fails with `["inclusive_bounds"]`, stop and report.
    - mystery_c: `width=16`, `height=16`, `bit_depth=24`, `header_size=18`, `row_stride=48`, `revision_path == []`.
    - mystery_d: `width=8`, `height=8`, `bit_depth=8`, `header_size=40`, `probe_name == "generic"`, `width_offset=0x04`, `width_format="<i"`, `height_offset=0x08`, `height_format="<i"`, `bit_depth_offset=0x0E`.
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 8.2 Write corpus tests for mystery_e through mystery_h in `tests/test_engine.py`
    - mystery_e: `width=8`, `height=8`, `bit_depth=8`, `header_size=86`, `revision_path == ["endianness_flip"]`. See Open Spec Conflict 2. If this fails, stop and report.
    - mystery_f: `width=12`, `height=10`, `bit_depth=8`, `header_size=12`, `probe_name == "generic"`, `width_offset=0x00`, `width_format="<I"`, `height_offset=0x04`, `height_format="<I"`, `bit_depth_offset=0x08`.
    - mystery_g: `width=8`, `height=8`, `bit_depth=24`, `header_size=20`, `probe_name == "generic"`, `width_offset=0x04`, `width_format="<H"`, `height_offset=0x06`, `height_format="<H"`, `bit_depth_offset=0x08`.
    - mystery_h: `width=6`, `height=6`, `bit_depth=8`, `header_size=128`, `row_stride=8`, `revision_path == ["inclusive_bounds","row_padding_variants"]`.
    - _Requirements: 7.5, 7.6, 7.7, 7.8_

  - [ ] 8.3 Write the all-eight and field round-trip corpus test in `tests/test_engine.py`
    - Parametrize over `mystery_a` to `mystery_h`. Assert each result is a `VerifiedHypothesis` and not a `FailureReport`, and that `check_closure(result.hypothesis, data)` passes.
    - For each result, assert every `FieldRecord` satisfies `struct.unpack_from(fr.fmt, data, fr.offset) == fr.value`.
    - For each result, assert `PrettyPrinter().render(result)` contains the exact closure string `{header_size} + {row_stride * height} = {total_file_size}`.
    - _Requirements: 7.9, 8.2, 8.3_

- [ ] 9. Property tests for the seven correctness properties
  - [ ] 9.1 Write Property 1 in `tests/test_engine.py`
    - **Property 1: Never Raises**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    - Define a shared `engine_inputs` strategy: `st.one_of(st.binary(max_size=65536), <corpus bytes with random byte flips, truncation and extension>)`. Mutating corpus bytes reaches the code paths that arbitrary bytes almost never reach.
    - `@given(engine_inputs)` with `@settings(max_examples=100, deadline=None)`. Assert `Engine().run(data)` returns a `VerifiedHypothesis` or `FailureReport`.
    - Tag: `Feature: structure-inference-engine, Property 1: never raises`

  - [ ] 9.2 Write Property 2 in `tests/test_engine.py`
    - **Property 2: Deadline Respected**
    - **Validates: Requirements 1.7, 6.5**
    - `@given(engine_inputs)` with `@settings(max_examples=100, deadline=None)`. Time `Engine(deadline_seconds=5.0).run(data)` with `time.monotonic()`. Assert a `HypothesisResult` is returned and elapsed time is below 5.25 seconds (0.25 s scheduling slack, stated in a comment).
    - Tag: `Feature: structure-inference-engine, Property 2: deadline respected`

  - [ ] 9.3 Write Property 3 in `tests/test_engine.py`
    - **Property 3: Closure Soundness**
    - **Validates: Requirements 1.1, 1.2, 1.4**
    - `@given(engine_inputs)` with `@settings(max_examples=100, deadline=None)`. When the result is a `VerifiedHypothesis`, assert `check_closure(v.hypothesis, data)` returns `(True, "", None)`. Add each of the eight corpus files as an `@example` so the assertion runs on a `VerifiedHypothesis` at least eight times.
    - Tag: `Feature: structure-inference-engine, Property 3: closure soundness`

  - [ ] 9.4 Write Property 4 in `tests/test_engine.py`
    - **Property 4: Field Round-Trip**
    - **Validates: Requirements 8.1, 8.2**
    - `@given(engine_inputs)` with `@settings(max_examples=100, deadline=None)`. When the result is a `VerifiedHypothesis`, assert `struct.unpack_from(fr.fmt, data, fr.offset) == fr.value` for every `FieldRecord` in `v.hypothesis.fields`. Add the eight corpus files as `@example`s.
    - Tag: `Feature: structure-inference-engine, Property 4: field round-trip`

  - [ ] 9.5 Write Property 5 in `tests/test_closure.py`
    - **Property 5: RLE Decoder Never Raises**
    - **Validates: Requirements 1.6, 6.3**
    - `@given(st.binary(max_size=65536), st.integers(min_value=0), st.integers(min_value=0, max_value=10**9))` with `@settings(max_examples=100)`, using `start = start % (len(data) + 1)`. Assert `rle_pcx_decode` returns an `RleResult` without raising. Also run with `start` outside `[0, len(data)]`.
    - This test runs against the typed `RleResult` introduced in task 2.1. design.md describes `bytes | None`, and this is the equivalent.
    - Tag: `Feature: structure-inference-engine, Property 5: RLE decoder never raises`

  - [ ] 9.6 Write Property 6 in `tests/test_closure.py`
    - **Property 6: RLE Output Bounded**
    - **Validates: Requirements 1.6**
    - Same generators as 9.5, with `max_output_bytes` limited to `[0, 4096]`. When `status == "ok"`, assert `len(result.data) == max_output_bytes`. When `status` is not `"ok"`, assert `result.data is None`.
    - Add a generator that builds valid RLE streams (runs and literals totalling a known length) so the `ok` branch is exercised, and assert the decoded length equals the known length.
    - Tag: `Feature: structure-inference-engine, Property 6: RLE output bounded`

  - [ ] 9.7 Write Property 7 in `tests/test_engine.py`
    - **Property 7: FailureReport Is Total**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - `@given(engine_inputs)` with `@settings(max_examples=100, deadline=None)`. When the result is a `FailureReport`, assert `len(rejections) >= 1`, `total_checks >= 0`, every entry has a non-empty `reason` and `source`, every entry with a `hypothesis` carries `fields` with offset and format, and for `len(data) < 3` the report has exactly one entry with `reason == "input_too_short"`.
    - Tag: `Feature: structure-inference-engine, Property 7: FailureReport is total`

- [ ] 10. Final checkpoint
  - Run `python -m pytest tests -q` and confirm all tests pass. Report any corpus failure tied to the Open Spec Conflicts section instead of changing behaviour. Ask the user if questions arise.

## Notes

- Offsets and formats come from requirements.md Requirement 2.1 and Requirement 4.3. The PCX probe follows Requirement 2.1 (`data[2]` in `{0, 1}` selects the encoding), not the superseded text in design.md.
- design.md specifies `rle_pcx_decode` returning `bytes | None`. The tasks use a typed `RleResult` so `check_closure` decodes once and can tell overrun from underrun.
- design.md shows `generic_search(data, check_fn, deadline_fn)`. The tasks use `over_limit`, `tick` and `on_reject` so the Engine's counter and deadline are shared.
- Several tasks edit the same file. The dependency graph places them in separate waves.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["2.3", "3.1"] },
    { "id": 5, "tasks": ["3.2", "4.1", "5.1", "9.5"] },
    { "id": 6, "tasks": ["3.3", "4.2", "5.2", "9.6"] },
    { "id": 7, "tasks": ["3.4", "4.3", "5.3"] },
    { "id": 8, "tasks": ["3.5", "4.4", "6.1"] },
    { "id": 9, "tasks": ["3.6", "4.5", "6.2"] },
    { "id": 10, "tasks": ["6.3"] },
    { "id": 11, "tasks": ["6.4"] },
    { "id": 12, "tasks": ["7.1", "8.1"] },
    { "id": 13, "tasks": ["7.2", "8.2"] },
    { "id": 14, "tasks": ["8.3"] },
    { "id": 15, "tasks": ["9.1"] },
    { "id": 16, "tasks": ["9.2"] },
    { "id": 17, "tasks": ["9.3"] },
    { "id": 18, "tasks": ["9.4"] },
    { "id": 19, "tasks": ["9.7"] }
  ]
}
```
