# Implementation Plan: Structure-Inference Engine

## Overview

Build the Structure-Inference Engine as a pure-Python, standard-library-only package under `necropsy/engine/`. Add a text renderer under `necropsy/report/` and a Kiro spec emitter under `necropsy/emit/`. The work runs bottom-up: types and budget, closure gate, probes, strategies, coherence, generic search, engine, corpus, engine properties, renderer, spec emission, final checkpoint.

Rules for every task:

- Copy byte offsets, struct formats, reason strings and output line formats verbatim from requirements.md and design.md. Do not change them.
- Every public function returns a structured value and never raises on any input. A last-resort `try/except Exception` is allowed at each entry point, but inner code must bounds-check every read and must not rely on it.
- No network calls. Standard library only in `necropsy/`. `pytest` and `hypothesis` are used in `tests/` only.
- No presentation code in `necropsy/engine/`. Rendering belongs in `necropsy/report/` and `necropsy/emit/`.
- Build only what the task asks for.
- The shell is Windows PowerShell 5.1. Use `;` between statements, never `&&`. Run tests with `python -m pytest tests/<file> -q`.
- Write files as UTF-8 without a BOM. Files under `.kiro/` are checked by `tools/check_no_bom.py` on commit.
- Import corpus helpers as `from tests.conftest import CORPUS_NAMES, corpus_bytes`. `tests/` is a package, so pytest loads its conftest as `tests.conftest`; a bare `from conftest import ...` fails or loads a second copy. Never copy the helper into a test file.
- Expected values in tests come from requirements.md and design.md, never from reading the implementation. If the spec does not state a value a test needs, report it as a spec gap instead of copying the code's behaviour.
- All tasks, including the property tests, are required.
- If a corpus test fails, stop and report the actual result. Do not change unrelated code to force a pass. The expected values were measured against a reference model of these rules, and are listed in design.md under "Corpus Trace (measured)".

## Tasks

- [x] 1. Scaffold, types and budget
  - [x] 1.1 Create the package skeleton and test configuration
    - Create the following, each empty unless stated:
      - `necropsy/__init__.py`
      - `necropsy/engine/__init__.py`
      - `necropsy/report/__init__.py`
      - `necropsy/emit/__init__.py`
      - `tests/__init__.py`
      - `tests/support/__init__.py`
      - `tests/conftest.py`
    - In `tests/conftest.py`:
      - Put the repo root and `spike/` on `sys.path`.
      - Add a `corpus` fixture that returns a dict from file name (`mystery_a` to `mystery_i`) to bytes, read from `spike/samples/`.
      - Add a `corpus_bytes(name)` helper.
    - Create `tests/support/inputs.py` with the shared Hypothesis strategies used by every engine-level property test:
      - `mutated_corpus()` takes a corpus file and applies byte flips, truncation and extension.
      - `engine_inputs = st.one_of(st.binary(max_size=65536), mutated_corpus())`.
    - _Requirements: 6.3, 6.5, 7.1_

  - [x] 1.2 Implement `necropsy/engine/types.py`
    - Implement, exactly as written in design.md "Data Models":
      - `REASONS` and `TERMINATIONS`
      - `FieldRecord`, `Hypothesis` and `hypothesis_key`
      - `RejectionEntry` and `Candidate`
      - `VerifiedHypothesis`, `AmbiguousResult` and `FailureReport`
      - `EngineResult`
    - All dataclasses are frozen. Collections are tuples.
    - Add the fixed `AMBIGUITY_REASON` template from design.md, with a `{n}` placeholder.
    - No business logic.
    - _Requirements: 5.5, 5.6, 5.7, 5.11, 8.1, 10.1, 10.2, 10.3_

  - [x] 1.3 Implement `necropsy/engine/budget.py`
    - `Budget(deadline_seconds, cap=10_000, clock=time.monotonic)` with `checks`, `stop_reason()` and `charge()`, exactly as written in design.md.
    - `stop_reason()` tests the deadline before the cap.
    - `charge()` increments `checks` only when it returns `None`.
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 1.4 Write unit tests for types and budget in `tests/test_engine.py`
    - `hypothesis_key` contains exactly `(width, height, bit_depth, header_size, row_alignment, encoding, data_end)`.
    - Each result type has the correct default `status`.
    - Results are immutable: assigning to a field raises `FrozenInstanceError`.
    - `Budget` with an injected fake clock:
      - The deadline fires at exactly `deadline_seconds`.
      - The cap fires after 10,000 `charge()` calls.
      - The deadline wins when both apply.
      - `checks` never exceeds the cap.
    - _Requirements: 3.3, 5.1, 5.3, 10.1_

- [x] 2. Closure gate
  - [x] 2.1 Implement `necropsy/engine/trailers.py`
    - `TrailerEntry`, `TRAILER_REGISTRY` and `match_trailer`, exactly as written in design.md "Trailer Registry".
    - The registry has one entry, `pcx_palette_256` (length 769, marker `0x0C`, applies to `pcx` and `generic`).
    - `match_trailer` takes an optional `registry` argument, so tests can add entries without editing the gate.
    - _Requirements: 1.3, 1.5, 1.6_

  - [x] 2.2 Implement `row_stride`, `RleResult`, `rle_pcx_decode` and `rle_pcx_output_length` in `necropsy/engine/closure.py`
    - Copy the pseudocode in design.md "Closure".
    - `row_stride` uses integer arithmetic only.
    - The decoder checks the run against the remaining output budget inside the loop, before writing.
    - The decoder returns `underrun` when a run marker is the last byte of the region.
    - The decoder returns `unconsumed` when the output is complete but region bytes remain.
    - The decoder returns `underrun` for out-of-range `start`/`end` or a negative `max_output_bytes`.
    - `rle_pcx_output_length` only counts; it allocates nothing.
    - _Requirements: 1.1, 1.8, 1.9, 1.10, 1.11_

  - [x] 2.3 Implement `ClosureVerdict` and `check_closure` in `necropsy/engine/closure.py`
    - Follow design.md "Closure":
      - Check for a degenerate hypothesis first.
      - Then take the declared `data_end` (and its bounds check), or `match_trailer` with the hypothesis's `probe_name` as origin.
      - Then apply the encoding branch. Any other encoding gives `unsupported_encoding`.
    - The `arithmetic_mismatch` discrepancy is `(data_end − header_size) − expected_decoded_bytes`.
    - Wrap the function so that any exception becomes a `ClosureVerdict` with reason `internal_error`.
    - _Requirements: 1.2, 1.3, 1.4, 1.7, 1.8, 1.12, 1.13, 1.14_

  - [x] 2.4 Write unit tests in `tests/test_closure.py`
    - `row_stride` cases:
      - width 4 at 1 bpp gives 1
      - width 9 at 1 bpp gives 2
      - width 16 at 24 bpp gives 48
      - width 6 at 8 bpp with alignment 4 gives 8
      - width 3 at 12 bpp gives 5
    - Decoder:
      - A literal and run mix returns `ok`.
      - A large run against a small `max_output_bytes` returns `overrun` with no output beyond the limit.
      - A trailing marker returns `underrun`.
      - Leftover input returns `unconsumed`.
      - `consumed_to` equals `end` on `ok`.
      - `consumed_to` on every non-`ok` status equals the value Requirement 1.11 states for that status.
    - `check_closure` reasons: one test for each of `degenerate_hypothesis`, `field_out_of_bounds`, `arithmetic_mismatch` (with a signed discrepancy), `decoder_overrun`, `decoder_underrun`, `decoder_unconsumed` and `unsupported_encoding`.
    - Trailers:
      - The PCX palette trailer is applied for origins `pcx` and `generic` and not for `tga`.
      - A test registry with an extra entry changes `match_trailer` results without any edit to `closure.py`.
    - Regression for the leftover-input defect, on the mystery_b bytes:
      - `rle_pcx` at 7×7, header 128, origin `pcx`, does not close, with reason `decoder_unconsumed` (Requirement 7.2).
      - With `encoding = "rle_pcx"` and origin `"pcx"`, at header 128, 8 bpp and alignment 1, the only closing `(width, height)` pairs with both values in 1..256 are the seven area-64 shapes 1×64, 2×32, 4×16, 8×8, 16×4, 32×2 and 64×1. The encoding and origin are fixed because the PCX palette trailer then applies and the RLE region [128, 186) decodes to 64 bytes. Under `"none"` the region is 58 bytes, so the closing shapes would have area 58, not 64.
    - _Requirements: 1.1–1.14_

  - [x] 2.5 Write property tests in `tests/test_closure.py`
    - **Property 6: RLE decoder is bounded and typed**
    - **Validates: Requirements 1.9, 1.10, 1.11, 6.4**
    - Generators:
      - `st.binary(max_size=65536)`
      - arbitrary integers for `start` and `end`
      - `max_output_bytes` in `[-10, 10**9]`
      - a second generator that builds valid RLE streams of known output length
    - Assert:
      - the result is an `RleResult` with a valid status;
      - `ok` implies `len(data) == max_output_bytes` and `consumed_to == end`;
      - every other status has `data is None`;
      - the valid-stream generator decodes to its known length.
    - Add a never-raises property for `check_closure` over arbitrary `Hypothesis` values (arbitrary ints, encodings from `{"none", "rle_pcx", "rle_tga", "x"}`, arbitrary `data_end`) and arbitrary bytes.
    - Use `@settings(max_examples=100)`.
    - Tag: `Feature: structure-inference-engine, Property 6: RLE decoder is bounded and typed`

- [x] 3. Probes
  - [x] 3.1 Implement the safe read helper, `ProbeOutcome` and the PCX probe in `necropsy/engine/probes.py`
    - `read(data, name, offset, fmt) -> FieldRecord | None` never raises. It returns `None` when `offset < 0` or `offset + struct.calcsize(fmt) > len(data)`.
    - `ProbeOutcome(seed, rejections)`.
    - `probe_pcx` follows Requirement 2.5 and the design.md probe table.
      - Seed: `width = xmax`, `height = ymax`, `header_size = 128`, alignment 1, `bounds = (xmin, ymin, xmax, ymax)`, `probe_name = "pcx"`.
      - Encoding: `"none"` for byte `0x02 == 0` and `"rle_pcx"` for 1.
    - When the precondition fails, attach `RejectionEntry("probe_precondition_failed", "pcx", seed, detail=...)` and still return the seed.
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Implement the TGA probe in `necropsy/engine/probes.py`
    - Follow Requirement 2.6.
    - Signature: byte `0x01 ∈ {0, 1}` and byte `0x02 ∈ {1, 2, 3, 9, 10, 11}`, with minimum length 18.
    - `header_size = 18 + id_length + color_map_type × color_map_length × ceil(color_map_entry_size / 8)`.
    - Encoding: `"none"` for image types 1–3 and `"rle_tga"` for 9–11.
    - Record `image_descriptor` at `0x11` as `B` on the seed. Report it only; it does not change inference (Decision Record item 14).
    - A precondition failure is attached and the seed is still returned.
    - _Requirements: 2.2, 2.3, 2.4, 2.6_

  - [x] 3.3 Implement the PBM probe in `necropsy/engine/probes.py`
    - Follow Requirement 2.7 and the design.md PBM parsing paragraph.
    - Parse only within `data[:1024]` and skip `#` lines.
    - The dimensions line must split into exactly two all-digit tokens.
    - Record `magic` as `3s` at 0. Record `width` and `height` as `<n>s` at their token offsets.
    - On parse failure, return a seed with `width = 0`, `height = 0`, `header_size = 3`, and `probe_precondition_failed`.
    - _Requirements: 2.2, 2.3, 2.4, 2.7_

  - [x] 3.4 Implement the TIFF probe in `necropsy/engine/probes.py`
    - Follow Requirement 2.8 and the design.md TIFF walk.
    - Honour the byte-order mark: every multi-byte read uses `<` for `II` and `>` for `MM`.
    - Read SHORT values as `oH` at entry + 8 and LONG values as `oI` at entry + 8.
    - Use only tags `{256, 257, 258, 259, 273, 277, 279}`, and only with type 3 or 4 and count 1.
    - Defaults: compression 1, samples_per_pixel 1.
    - Seed:
      - `bit_depth = bits_per_sample × samples_per_pixel`
      - `header_size = strip_offset`
      - `data_end = strip_offset + strip_byte_count`
      - `encoding = "none"` for compression 1, otherwise `"tiff_compression_<n>"`
    - An out-of-bounds IFD or entry table records `field_out_of_bounds` and still returns a seed from the values read.
    - A missing required tag or `samples_per_pixel ≠ 1` records `probe_precondition_failed`.
    - Export `PROBES = (("pcx", probe_pcx), ("tga", probe_tga), ("pbm", probe_pbm), ("tiff", probe_tiff))`.
    - _Requirements: 2.2, 2.3, 2.4, 2.8_

  - [x] 3.5 Write unit tests in `tests/test_probes.py`
    - PCX:
      - mystery_b gives seed 7×7, `encoding = "rle_pcx"`, bounds `(0, 0, 7, 7)`.
      - mystery_i gives `encoding = "none"`.
      - mystery_h gives 5×5.
      - Byte `0x02 == 2` gives `None`.
      - A crafted header with `xmax < xmin` returns a seed plus `probe_precondition_failed`.
    - TGA:
      - mystery_c gives 16×16, 24 bpp, header 18, and an `image_descriptor` `FieldRecord` at `0x11`, format `B`, value `(0x20,)`.
      - mystery_b gives `None`, because byte `0x01 = 5` is not a valid colour-map type.
      - A crafted colour-mapped header gives the colour-map header size.
      - Image type 10 gives `"rle_tga"`.
    - PBM:
      - mystery_a gives 4×4, header 7, with fields `magic` `3s`, `width` `1s` at 3 and `height` `1s` at 5.
      - A header with a `#` comment parses.
      - A malformed header returns the zero seed plus `probe_precondition_failed`.
    - TIFF:
      - mystery_e gives 8×8, 8 bpp, header 86, `data_end` 150, with every multi-byte format starting with `>`.
      - A crafted `II` file parses with `<` formats.
      - A crafted file with `ifd_offset` past the end returns a seed plus `field_out_of_bounds`.
      - Compression 5 gives `"tiff_compression_5"`.
    - Every `FieldRecord` from every probe round-trips through `struct.unpack_from`.
    - Build crafted inputs in code, from documented layouts.
    - _Requirements: 2.1–2.8, 8.1, 8.2_

  - [x] 3.6 Write never-raises property tests in `tests/test_probes.py`
    - **Property: each probe never raises on arbitrary bytes**
    - **Validates: Requirements 2.3, 6.4, 6.7**
    - For each probe:
      - `@given(st.binary(max_size=65536))`
      - a second generator that prefixes the probe's signature bytes to arbitrary bytes
    - Assert the result is `None` or a `ProbeOutcome` whose seed is a `Hypothesis`, and whose `FieldRecord`s all round-trip.
    - Use `@settings(max_examples=100)`.
    - Tag: `Feature: structure-inference-engine, Probe never raises`

- [x] 4. Revision strategies
  - [x] 4.1 Implement `necropsy/engine/strategies.py`
    - Implement `inclusive_bounds`, `rle_pcx`, `row_padding_variants` and `STRATEGIES`, exactly as written in design.md "Revision strategies", using `dataclasses.replace`.
    - `rle_pcx` applies only when `probe_name == "pcx"` and `encoding == "none"`.
    - `row_padding_variants` yields alignments 2 then 4, skipping the current alignment.
    - Each strategy is wrapped so that an exception returns `()`.
    - There are no other strategies. Do not implement endianness, field-width or header-length revision.
    - _Requirements: 3.1, 3.7_

  - [x] 4.2 Write unit tests in `tests/test_strategies.py`
    - `inclusive_bounds`:
      - bounds `(0, 0, 7, 7)` give 8×8;
      - with no bounds it gives `()`.
    - `rle_pcx`:
      - a PCX hypothesis with `none` gives `rle_pcx`;
      - a TGA hypothesis gives `()`;
      - a PCX hypothesis that is already `rle_pcx` gives `()`.
    - `row_padding_variants`:
      - from alignment 1 it gives `(2, 4)` in that order;
      - from alignment 4 it gives `(2,)`.
    - Each candidate's `revision_path` equals the parent's path plus the strategy name, and the parent is unchanged.
    - `STRATEGIES` names are exactly `("inclusive_bounds", "rle_pcx", "row_padding_variants")`.
    - _Requirements: 3.1, 3.7_

  - [x] 4.3 Write a never-raises property test in `tests/test_strategies.py`
    - **Property: each strategy never raises**
    - **Validates: Requirements 6.4, 6.7**
    - Generate arbitrary `Hypothesis` values with arbitrary ints, optional bounds, probe names from the five origins, and encodings from `{"none", "rle_pcx", "rle_tga"}`.
    - Assert each strategy returns a tuple of `Hypothesis`.
    - Use `@settings(max_examples=100)`.
    - Tag: `Feature: structure-inference-engine, Strategy never raises`

- [x] 5. Row coherence
  - [x] 5.1 Implement `necropsy/engine/coherence.py`
    - Implement `row_coherence(decoded, height, row_stride) -> tuple[float | None, str]`, `COHERENCE_METHOD` and `COHERENCE_SIZE_LIMIT`, exactly as written in design.md "Row coherence".
    - The docstring names the three failure modes.
    - Pair sampling is `random.Random(0).sample(range(P), 1024)` when `P > 1024`.
    - `pair_at(k, h)` uses binary search.
    - Size limit gives `not_computed`. `height < 2` or a zero baseline gives `unscorable`.
    - Add `coherence_gap(scores) -> float | None`.
    - Wrap the function so an exception returns `(None, "unscorable")`.
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 5.2 Write unit tests in `tests/test_coherence.py`
    - A hand-computed 3-row example gives the exact `adjacent / baseline` value.
    - Identical rows give `unscorable`. One row gives `unscorable`.
    - 262,145 expected bytes give `not_computed`.
    - With more than 1,024 pairs (height 50), the result is identical across two calls, and `pair_at` matches a brute-force lexicographic enumeration for every `k`.
    - `coherence_gap`:
      - `[0.2, 0.25]` gives 0.2;
      - fewer than two scores gives `None`;
      - a second-lowest score of 0 gives `None`.
    - The docstring contains all three failure-mode statements.
    - _Requirements: 11.2–11.7_

  - [x] 5.3 Write a property test in `tests/test_coherence.py`
    - **Property 14: Coherence function is total**
    - **Validates: Requirements 11.2, 11.3, 11.4, 6.4**
    - Inputs: arbitrary bytes up to 65,536, `height` in `[-5, 70000]`, `row_stride` in `[-5, 70000]`.
    - Assert the result is `(finite float ≥ 0, "scored")`, `(None, "unscorable")` or `(None, "not_computed")`.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tag: `Feature: structure-inference-engine, Property 14: Coherence function is total`

- [x] 6. Generic Search
  - [x] 6.1 Implement `necropsy/engine/generic.py`
    - Implement `HEADER_LENGTHS = tuple(range(4, 257, 4))`, `WIDTH_HEIGHT_FORMATS`, `VALID_BIT_DEPTHS`, `GenericOutcome(found, stop)` and `generic_search(data, budget, on_reject)`, exactly as written in design.md "Generic Search".
    - Group reads by value.
    - Width plus bit depth fixes the height.
    - `rle_pcx` is tried only when a registered trailer matched.
    - Every equivalent read becomes a `FieldRecord`.
    - Check `budget.stop_reason()` at the start of each header length and `budget.charge()` before each closure check.
    - Collect every closer and do not return early.
    - Enumeration order is deterministic.
    - The function never raises.
    - _Requirements: 4.1–4.9, 5.1, 5.3_

  - [x] 6.2 Write unit tests in `tests/test_generic.py`
    - Use a `Budget` with a far deadline.
    - mystery_d:
      - The found set includes key `(8, 8, 8, 40, 1, "none", None)`.
      - The found set has 18 entries, matching the measured value in design.md. If the count differs, report it.
    - mystery_f:
      - The set includes `(12, 10, 8, 12, 1, "none", None)`.
      - That candidate's `width` records include offset 0 with at least two of `<H`, `<I` and `<i`, all with value 12.
      - The set has 8 entries.
    - mystery_g:
      - The set includes `(8, 8, 24, 20, 1, "none", None)`.
      - The set has 8 entries.
    - Two calls give identical ordered results.
    - A `Budget` with a cap of 3 stops with `search_cap_exceeded` after 3 checks.
    - An injected clock that is already past the deadline stops with `deadline_exceeded` before any check.
    - `HEADER_LENGTHS` runs from 4 to 256 in steps of 4.
    - _Requirements: 4.2–4.9, 7.4, 7.6, 7.7_

  - [x] 6.3 Write property tests in `tests/test_generic.py`
    - **Property: Generic Search never raises and respects the cap**
    - **Validates: Requirements 4.8, 5.3, 6.4, 6.7**
    - Use `@given(st.binary(max_size=65536))` with a cap of 10,000.
    - Assert:
      - the result is a `GenericOutcome`;
      - `budget.checks ≤ 10,000`;
      - every found candidate closes under `check_closure`;
      - all `FieldRecord`s sharing a name agree on the value.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tag: `Feature: structure-inference-engine, Generic search never raises`

- [x] 7. Engine
  - [x] 7.1 Implement the probe phase and candidate assembly in `necropsy/engine/engine.py`
    - `Engine(deadline_seconds=5.0, clock=time.monotonic)`.
    - `run()` creates one `Budget` and one ordered rejection list.
    - An input shorter than 3 bytes returns `FailureReport("input_too_short", ...)` with exactly one `input_too_short` entry, and runs no probe.
    - Run every probe in `PROBES`, checking `budget.stop_reason()` before each one. Record probe rejections, charge one check per seed, and close-check each seed.
    - `_candidate(h, verdict, budget)` checks `stop_reason()`, then calls `row_coherence` and builds a `Candidate`.
    - `_outcome(winners, stage)`:
      - one winner gives `VerifiedHypothesis`;
      - more than one gives `AmbiguousResult` with `AMBIGUITY_REASON` and `coherence_gap`, keeping discovery order.
    - _Requirements: 2.1, 2.9, 5.1, 5.8, 5.9, 5.11, 10.1–10.5, 11.1, 11.5, 11.6_

  - [x] 7.2 Implement the revision phase in `necropsy/engine/engine.py`
    - Follow the BFS in design.md "Revision phase".
    - The `seen` map starts with every seed key at depth 0.
    - Loop order is pinned (Requirement 3.2): hypotheses of the frontier are the outer loop, strategies in `STRATEGIES` order the inner loop. This defines the canonical path only.
    - Add `alternative_paths: tuple[tuple[str, ...], ...] = ()` to `Candidate` in `necropsy/engine/types.py`, as in design.md "Data Models".
    - When a skipped candidate's key was first produced at the same depth, append its path to that key's alternatives. Build closing candidates after the depth completes, passing their alternatives.
    - Charge before each check.
    - Collect all winners at the first closing depth and stop there.
    - Rejection source is `"revision:" + "->".join(path)`.
    - If nothing closes by depth 3, return `FailureReport("exhausted")`. Never enter Generic Search afterwards.
    - _Requirements: 3.2–3.10, 5.9_

  - [x] 7.3 Implement generic dispatch, termination and the never-raise wrapper in `necropsy/engine/engine.py`
    - Run `generic_search` only when no probe matched.
    - `on_reject` appends `RejectionEntry(..., source="generic")`.
    - A stop reason anywhere returns `FailureReport(stop, rejections, budget.checks, len(data), partial_candidates)`. Partial candidates keep any coherence already computed (`scored` or `unscorable`); only those whose coherence step never ran are `not_computed` (Decision Record item 13).
    - Wrap `run()` so any exception gives `FailureReport("internal_error", (RejectionEntry("internal_error", "engine", detail="<Class>: <msg>"),), 0, size)`.
    - Export from `necropsy/engine/__init__.py`:
      - `Engine` and `Budget`
      - `check_closure` and `row_stride`
      - every type in `types.py`
    - _Requirements: 4.1, 4.8, 5.2, 5.3, 5.10, 6.1, 6.2, 6.3_

  - [x] 7.4 Write unit tests in `tests/test_engine.py`
    - `b""` and a 2-byte input give `FAILED / input_too_short` with one entry.
    - A probe monkeypatched to raise gives `FAILED / internal_error` with detail starting with the class name.
    - An injected clock past the deadline on mystery_c gives `FAILED / deadline_exceeded`.
    - Cap: with `Budget` monkeypatched to a cap of 1 on mystery_h, the run gives `FAILED / search_cap_exceeded`.
    - Collect-all in the probe phase: two monkeypatched probes whose seeds both close give `UNRESOLVED_AMBIGUITY` with stage `probe`.
    - Collect-all in the revision phase: a monkeypatched strategy set where two distinct candidates close at depth 1 gives `UNRESOLVED_AMBIGUITY` with stage `revision`. Reordering the strategies gives the same candidate set.
    - Dedup: a spy on `check_closure` shows no key checked twice on mystery_h.
    - Rejection order is probe entries, then revision entries.
    - `partial_candidates`: a winner found before a deadline stop appears in `partial_candidates`. A partial candidate whose coherence was computed before the stop reports that score with `coherence_status = "scored"`; one whose coherence step never ran reports `"not_computed"` with score `None` (Requirement 11.4, Decision Record item 13).
    - _Requirements: 2.9, 3.3–3.6, 5.1–5.10, 6.1, 6.2, 10.4_

- [x] 8. Corpus
  - [x] 8.1 Expose pixel content in `spike/make_samples.py`
    - Refactor so the pixel content each builder writes is available as functions, without changing any output byte:
      - `pcx_rle_rows()` gives the 64 decoded bytes behind mystery_b and mystery_i;
      - `pixels(name)` gives the decoded bytes for each `RESOLVED` corpus file.
    - Verify the change: after running `python spike/make_samples.py`, all nine files match the committed versions byte for byte (`git diff --quiet spike/samples`).
    - _Requirements: 7.10_

  - [x] 8.2 Write corpus tests in `tests/test_corpus.py`
    - One test per corpus file asserting exactly Requirements 7.1–7.9: status, stage, probe or `"generic"`, width, height, bit depth, header size, row stride or alignment, encoding, data region, trailer and revision path.
    - For mystery_d, mystery_f and mystery_g, assert:
      - `UNRESOLVED_AMBIGUITY` with stage `generic`;
      - the true key is in the candidate keys;
      - no assertion on order or rank.
    - For mystery_f, assert the equivalent-width-read condition in Requirement 7.6.
    - For mystery_b, assert the rejection list contains the PCX seed's `decoder_unconsumed` rejection with source `pcx` (Requirement 7.2).
    - For mystery_c, assert the `image_descriptor` `FieldRecord` is at `0x11`, format `B`, value `(0x20,)`, and round-trips (Requirement 7.3).
    - For mystery_h and mystery_i, assert the exact canonical `revision_path` and that `alternative_paths` contains the reversed-order path (Requirements 7.8, 7.9).
    - For every `RESOLVED` file, `candidate.decoded == make_samples.pixels(name)` exactly.
    - No corpus file is `FAILED`.
    - _Requirements: 7.1–7.11_

- [x] 9. Engine property tests in `tests/test_engine_properties.py`
  - [x] 9.1 Write Properties 1 and 2
    - **Property 1: Never raises**
    - **Validates: Requirements 6.2, 6.3, 6.5**
    - **Property 2: Deadline bound**
    - **Validates: Requirements 5.4, 6.6**
    - Import `engine_inputs` from `tests/support/inputs.py` (task 1.1).
    - Property 1 asserts the return type is one of the three results.
    - Property 2 times `Engine(deadline_seconds=5.0).run` with `time.monotonic()` and asserts it returns in under 5.25 s. Comment the 0.25 s margin.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tags: `Feature: structure-inference-engine, Property 1: Never raises` and `Property 2: Deadline bound`

  - [x] 9.2 Write Properties 3, 4 and 5
    - **Property 3: Closure soundness**
    - **Validates: Requirements 1.7, 1.8, 1.14, 10.2, 10.3**
    - **Property 4: Field round-trip**
    - **Validates: Requirements 8.1, 8.2**
    - **Property 5: Equivalent reads agree**
    - **Validates: Requirements 4.7, 8.3**
    - Over `engine_inputs`, with every corpus file added via `@example`, for every candidate of a successful result:
      - `check_closure` re-verifies it, with matching data region and decoded bytes;
      - every `FieldRecord` round-trips;
      - records sharing a name agree on the value.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tags: `Property 3: Closure soundness`, `Property 4: Field round-trip`, `Property 5: Equivalent reads agree`

  - [x] 9.3 Write Properties 7, 9 and 10
    - **Property 7: Outcome well-formed**
    - **Validates: Requirements 5.6, 5.7, 10.1, 10.2, 10.3**
    - **Property 9: No duplicate hypotheses**
    - **Validates: Requirements 3.3**
    - **Property 10: Deterministic**
    - **Validates: Requirements 3.6**
    - **Property 15: Alternative paths are well-formed**
    - **Validates: Requirements 3.6, 3.9, 3.10**
    - Over `engine_inputs` with the corpus examples:
      - status matches the type and the candidate counts;
      - terminations and reasons are in the vocabularies;
      - candidate keys are distinct;
      - a `check_closure` spy sees no key twice;
      - two runs give equal results;
      - every alternative path has the same length as `revision_path`, differs from it and does not repeat; probe and generic candidates have none; every permutation of `STRATEGIES` (monkeypatched) gives the same outcome, candidate keys and set of paths per candidate.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tags: `Property 7: Outcome well-formed`, `Property 9: No duplicate hypotheses`, `Property 10: Deterministic`, `Property 15: Alternative paths are well-formed`

  - [x] 9.4 Write Property 8
    - **Property 8: Coherence cannot change the outcome**
    - **Validates: Requirements 10.5, 11.1, 11.8**
    - Over `engine_inputs` with the corpus examples, plus `st.randoms()`:
      - monkeypatch `row_coherence` in `necropsy.engine.engine` to return arbitrary `(score, "scored")` values from the drawn random;
      - assert status, candidate keys and candidate order equal those of an unpatched run.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tag: `Property 8: Coherence cannot change the outcome`

- [x] 10. Pretty printer
  - [x] 10.1 Implement `necropsy/report/pretty.py`
    - `render(result) -> str` produces exactly the lines in Requirements 8.4–8.6:
      - `RESOLVED` field table with offset as `0x%04X`;
      - the two closure-line forms;
      - the `trailer:` line, the `revision_path:` line, and the `alternative_paths:` line when non-empty;
      - the `UNRESOLVED_AMBIGUITY` header, stage, numbered candidates and coherence wording, with no candidate marked as preferred;
      - the `FAILED: {termination}` header, counts and numbered rejections with `(discrepancy=N)`.
    - Wrap the function so an exception returns `"render error: <Class>"`.
    - Nothing under `necropsy/engine/` imports this module.
    - _Requirements: 8.4, 8.5, 8.6, 8.7_

  - [x] 10.2 Write tests in `tests/test_pretty.py`
    - mystery_e: assert the exact `none` closure line `closure: [86, 150) holds 64 bytes = 8 x 8`.
    - mystery_b: assert the exact `rle_pcx` closure line and `trailer: pcx_palette_256`.
    - mystery_d: assert the ambiguity header with the correct count, every candidate numbered, every coherence line labelled as heuristic, and no words like "best" or "preferred".
    - A `FailureReport` from `b"\x00"`: assert `FAILED: input_too_short`.
    - Rendering twice gives the same string.
    - **Property 13: Pretty printer is total**
    - **Validates: Requirements 8.4, 8.5, 8.6, 8.7**
    - Over `engine_inputs`, `render(run(data))` returns a string whose first line starts with the status. Use `@settings(max_examples=100, deadline=None)`.
    - Tag: `Feature: structure-inference-engine, Property 13: Pretty printer is total`

- [x] 11. Spec emission
  - [x] 11.1 Implement `necropsy/emit/layout.py`
    - `build_layout(result, data) -> dict` in schema `necropsy-layout/1`, exactly as written in design.md "Layout schema":
      - kinds `format`, `file` and `ambiguous`;
      - the per-origin table for PCX, TGA, TIFF, PBM and generic;
      - expressions, `@` byte-order formats, encoding maps, trailers, `equivalent_reads` and `observed`.
    - Slug: the probe name, or `unknown-<sha256[:8]>`.
    - _Requirements: 9.2, 9.6, 9.7, 9.8, 9.9_

  - [x] 11.2 Implement `render_requirements` in `necropsy/emit/render.py`
    - Use the Kiro requirements structure from design.md "Emitted requirements.md".
    - Include one EARS criterion per field and tag entry, with name, hex offset, format, endianness and size.
    - State the data region, trailer, encoding and closure rule.
    - Include the observed-value criteria.
    - Put exactly one `necropsy-layout` block in the Introduction.
    - For PBM, include prose text-header rules.
    - For generic results, state explicitly that the layout is one file's, not a format's.
    - For results whose path contains `rle_pcx`, state that the encoding declaration was overridden.
    - For ambiguous results, write one `WHERE candidate k …` requirement per candidate, plus the cannot-separate requirement naming the three coherence failure modes. Assert no candidate.
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

  - [x] 11.3 Implement `render_design` in `necropsy/emit/render.py`
    - Use the Kiro design headings.
    - Include: structure tables, stage, source, revision path, data region, trailer, closure line, heuristic-labelled coherence, and numbered rejections.
    - List at most 500 rejections, followed by `… and N more not listed`.
    - _Requirements: 9.10_

  - [x] 11.4 Implement `render_tests` in `necropsy/emit/render.py`
    - Generate `test_<module>.py` (`<module>` = slug with `-` replaced by `_`) from the template in design.md "Emitted test_<module>.py", importing `parser_<module>`. Emit no pytest configuration file.
    - Embed the source as base64 when it is at most 65,536 bytes; otherwise set `SOURCE = None` and skip the fixture test.
    - For ambiguous results, target `parse_candidates` and `EXPECTED_CANDIDATES`.
    - The generated source must compile with `compile()`.
    - _Requirements: 9.11, 9.12_

  - [x] 11.5 Implement `necropsy/emit/emit.py` and exports
    - `EmittedSpec`, `EmitError`, `emit_spec(result, data)` (pure) and `write_spec(spec, out_dir, overwrite=False)`, exactly as written in design.md "Spec emission".
    - `write_spec` enforces:
      - the `^[a-z0-9-]+$` slug check;
      - the resolved path must stay inside `out_dir`;
      - no overwrite unless `overwrite=True`;
      - UTF-8 without BOM.
    - A `FailureReport` gives `EmitError`.
    - Both functions are wrapped so they never raise.
    - Export from `necropsy/emit/__init__.py`.
    - _Requirements: 9.1, 9.2, 9.13, 9.14, 9.15_

  - [x] 11.6 Implement `tests/support/reference_reader.py`
    - A generic interpreter of `necropsy-layout/1`, as described in design.md "Reference reader". It imports only `json`, `re` and `struct`.
    - Functions:
      - `extract_layout(markdown)`
      - `parse(layout, data)`, which follows the parser contract and decodes `none` only
      - `parse_candidates(layout, data)`
      - `make_parser_module(markdown)`, which returns module source embedding the markdown
    - It contains no knowledge of any specific format.
    - _Requirements: 9.16, 9.17, 9.18_

  - [x] 11.7 Write unit tests in `tests/test_emit.py`
    - Slugs:
      - mystery_e gives `tiff`, mystery_b gives `pcx`, mystery_a gives `pbm`;
      - mystery_d gives `unknown-` followed by its SHA-256 prefix.
    - Each emitted spec has exactly three files.
    - `requirements.md` has exactly one layout block, and its JSON has `schema == "necropsy-layout/1"`.
    - Layout kinds:
      - mystery_e is `format` and includes `byte_order` and `tag_table`;
      - mystery_a is `file`;
      - mystery_d is `ambiguous` with 18 candidates.
    - mystery_b's width rule is the inclusive-bounds expression.
    - mystery_i's spec states the encoding declaration was overridden.
    - mystery_d's requirements state every candidate and the cannot-separate statement, and assert no single candidate.
    - The generated `test_<module>.py` compiles for every successful corpus file, and the emitted file names are exactly `requirements.md`, `design.md` and `test_<module>.py`.
    - A `FailureReport` gives `EmitError` and nothing is written.
    - `write_spec`:
      - refuses an existing folder without `overwrite`;
      - rejects slug `../x`;
      - writes no BOM;
      - writes only the three files inside `tmp_path`.
    - The reference reader source contains no `necropsy` import.
    - _Requirements: 9.1–9.15_

  - [x] 11.8 Write acceptance tests in `tests/test_emit_acceptance.py`
    - mystery_e:
      - Emit the spec.
      - Pass only the emitted `requirements.md` text to the reference reader.
      - Parse mystery_e's bytes.
      - Assert width 8, height 8, bit depth 8, data region `[86, 150)`, and pixels equal to the engine's `candidate.decoded`.
    - Emitted tests under pytest, for mystery_c and mystery_e:
      - Write `parser_<slug>.py` from `make_parser_module(requirements.md)` and the emitted `test_<module>.py` into `tmp_path`.
      - Run `python -m pytest <tmp_path> -q` against the directory, not the file, in a subprocess with `PYTHONPATH=<tmp_path>`. This proves default collection works. Assert at least one test passed.
      - Assert exit code 0.
    - mystery_d: `parse_candidates` on the emitted layout includes the true layout (8×8, 8 bpp, start 40).
    - _Requirements: 9.16, 9.17, 9.18_

  - [x] 11.9 Write emission property tests in `tests/test_emit.py`
    - **Property 11: Spec emitter is total**
    - **Validates: Requirements 9.1, 9.6, 9.13, 6.4**
    - **Property 12: Emitted layout reproduces the engine**
    - **Validates: Requirements 9.16, 9.18**
    - Over `engine_inputs` with the corpus examples:
      - `emit_spec(run(data), data)` never raises;
      - it returns `EmittedSpec` exactly when the result is successful;
      - the spec has three files and one parseable layout block.
    - For results with `encoding == "none"`, the reference reader reproduces every candidate's dimensions, data region and decoded bytes.
    - Use `@settings(max_examples=100, deadline=None)`.
    - Tags: `Property 11: Spec emitter is total` and `Property 12: Emitted layout reproduces the engine`

- [x] 12. Final checkpoint
  - Run `python -m pytest tests -q`. All tests must pass.
  - Emit the specs for mystery_e and mystery_d into a temporary directory. Run Kiro's spec format validator on each emitted `requirements.md` and `design.md`, and report any issue. (Requirement 9.19)
  - Run `python tools/check_no_bom.py`.
  - Re-run the corpus and the three 65,536-byte inputs from design.md "Measured Performance" against the implementation, and report the measured times next to the recorded ones.
  - Ask the user if questions arise.
  - _Requirements: 5.4, 9.19_

- [x] 13. TGA 2.0 footer in the Trailer Registry
  - [x] 13.1 Generalise `TrailerEntry` and add `tga2_footer` in `necropsy/engine/trailers.py`
    - `TrailerEntry(name, length, signature: bytes, signature_offset: int, applies_to)` and `match_trailer`, exactly as in design.md "Trailer Registry".
    - `pcx_palette_256` becomes signature `b"\x0c"` at offset 0, with unchanged behaviour.
    - Add `tga2_footer`: length 26, signature `b"TRUEVISION-XFILE.\x00"` at offset 8, applies to `tga` and `generic`.
    - In `necropsy/engine/generic.py`, try `rle_pcx` only when the matched trailer is `pcx_palette_256` (Requirement 4.5).
    - The TGA probe and `check_closure` are unchanged.
    - _Requirements: 1.3, 1.5, 1.6, 4.5_

  - [x] 13.2 Update spec emission for signature trailers
    - Layout trailers use `{"name", "length", "signature" (hex), "signature_offset"}` (design.md "Layout schema"). Update `necropsy/emit/layout.py`, `tests/support/reference_reader.py` and any trailer wording in `necropsy/emit/render.py`.
    - TGA layouts list `tga2_footer`.
    - _Requirements: 9.5, 9.6, 9.16_

  - [x] 13.3 Write tests for the footer
    - `tests/test_closure.py`: both registry entries in order; `tga2_footer` matches for origins `tga` and `generic` and not `pcx`; a one-byte change to the signature stops the match; the existing `pcx_palette_256` tests still pass unchanged.
    - `tests/test_corpus.py`: `external_b` per Requirement 7.12, including the data region `[18, 9234)`, trailer `tga2_footer`, `image_descriptor` `(0x00,)`, and decoded bytes equal to `source.ppm` stored bottom row first in BGR order. The nine `mystery_*` results are unchanged.
    - `tests/test_emit.py`: the emitted TGA layout lists `tga2_footer` with its signature, and the reference reader reproduces `external_b` from the emitted `requirements.md` alone.
    - _Requirements: 1.5, 4.5, 7.12, 9.16_

  - [x] 13.4 Update `tests/ui/test_external.py` for the resolved finding
    - Its own comment says the strict xfail must be removed when the engine gains a TGA footer entry. Remove it, and replace the finding test with one asserting `external_b` resolves with trailer `tga2_footer`.
    - If the UI-level assertions in the formerly xfailed test fail for a UI reason, report it; do not change UI code in this spec.
    - _Requirements: 7.12_

- [x] 14. Header overlap rule and file layouts for rule-breaking files
  - [x] 14.1 Reject header and data overlap in `check_closure`
    - Implement Requirement 12 in `necropsy/engine/closure.py` exactly as design.md "Closure": after `data_end` is known and before decoding, reject with `degenerate_hypothesis` when the data region intersects any of the hypothesis's own `FieldRecord` byte ranges.
    - Add tests to `tests/test_closure.py` from Requirement 12: a crafted hypothesis whose data region covers one of its fields is rejected; a field placed after the data region is not; a hypothesis with no fields is unaffected. Build inputs in code.
    - Run the full corpus. If any of the nine `mystery_*` results or `external_b` changes in any way (status, candidates, candidate counts 18/8/8, paths, checks), stop and report it; do not adjust expectations.
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 14.2 Emit rule-breaking probe results as file layouts
    - Implement Requirement 9.20 in `necropsy/emit/layout.py` (layout kind `file` with literal values) and the "describes this one file only" statement in the emitted documents.
    - Add tests to `tests/test_emit.py` from Requirement 9.20: a crafted TIFF whose probe records `probe_precondition_failed` and which still resolves emits kind `file`, states it describes one file only, and the reference reader reproduces it from the emitted `requirements.md` alone. mystery_e still emits kind `format`.
    - _Requirements: 9.20, 9.16_

- [ ] 15. Truthful emitted-suite text, a zero-check termination, and timing
  - [-] 15.1 Verify and correct the acceptance-suite text in `necropsy/emit/render.py`
    - Print verbatim the text `_acceptance_line` emits for a single result (mystery_e) and an ambiguous one (mystery_d).
    - Measure: run plain `python -m pytest <folder> -q` in an emitted folder with nothing added, and again with the reference parser module beside it. Record both outcomes exactly.
    - Where the emitted text claims anything the measurement contradicts, fix the text, not the measurement.
    - _Requirements: 9.1, 9.11, 9.17_

  - [x] 15.2 Add termination `no_hypothesis_checked`
    - Add it to `TERMINATIONS` in `necropsy/engine/types.py` and return it from `necropsy/engine/engine.py` exactly when Requirement 5.12 says. `exhausted` keeps its meaning.
    - Tests from Requirement 5.12: a zero-check input (e.g. 65,536 random bytes, or a short text file) gives `no_hypothesis_checked`; an input whose hypotheses are checked and none closes still gives `exhausted`. Update any existing test that asserted `exhausted` for a zero-check input, citing Requirement 5.12.
    - Re-run the nine `mystery_*` files and `external_b` against a recorded baseline. If any result changes, stop and report.
    - _Requirements: 5.7, 5.12, 4.8_

  - [~] 15.3 Re-time the three 65,536-byte inputs
    - Time them once with nothing else running and report against design.md "Measured Performance". Do not optimise.
    - _Requirements: 5.4_

## Notes

- The expected corpus values and candidate counts (18, 8 and 8) come from a reference model of these exact rules, recorded in design.md. A mismatch means the implementation and the spec disagree; report it, do not tune either.
- Coherence never affects the outcome. Property 8 enforces this.
- Tasks 10.1 and 10.2 (pretty printer) run in the last waves, immediately before task 12, so they block nothing. They stay in this spec because task 11.3 references the closure line from Requirement 8.4. See the requirements Decision Record item 11.
- `header_length_scan`, `endianness_flip` and `field_width_variants` were deliberately removed from revision. See the requirements Decision Record. Do not reintroduce them.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "8.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "11.6"] },
    { "id": 2, "tasks": ["1.4", "2.1", "2.2", "3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["2.3", "3.2", "4.2", "5.2"] },
    { "id": 4, "tasks": ["2.4", "3.3", "4.3", "5.3"] },
    { "id": 5, "tasks": ["2.5", "3.4", "6.1"] },
    { "id": 6, "tasks": ["3.5", "6.2", "7.1"] },
    { "id": 7, "tasks": ["3.6", "6.3", "7.2"] },
    { "id": 8, "tasks": ["7.3"] },
    { "id": 9, "tasks": ["7.4", "8.2", "11.1"] },
    { "id": 10, "tasks": ["9.1", "11.2"] },
    { "id": 11, "tasks": ["9.2", "11.3"] },
    { "id": 12, "tasks": ["9.3", "11.4"] },
    { "id": 13, "tasks": ["9.4", "11.5"] },
    { "id": 14, "tasks": ["11.7", "11.8"] },
    { "id": 15, "tasks": ["11.9"] },
    { "id": 16, "tasks": ["10.1"] },
    { "id": 17, "tasks": ["10.2"] },
    { "id": 18, "tasks": ["13.1"] },
    { "id": 19, "tasks": ["13.2"] },
    { "id": 20, "tasks": ["14.1"] },
    { "id": 21, "tasks": ["14.2"] },
    { "id": 22, "tasks": ["13.3"] },
    { "id": 23, "tasks": ["13.4"] },
    { "id": 24, "tasks": ["15.1", "15.2"] },
    { "id": 25, "tasks": ["15.3"] },
    { "id": 26, "tasks": ["12"] }
  ]
}
```