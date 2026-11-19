# Test audit: tautology check

Scope: `tests/test_closure.py` (23 tests) and `tests/test_strategies.py` (10 tests),
as committed at `480b712`. Report only; nothing was changed.

## Method

For each test I asked where its expected value comes from:

- **Spec**: the value follows from a rule in `requirements.md` (or the task text in
  `tasks.md`, which cites those requirements). The test is an independent oracle.
- **Design convention**: the value is not a behavioural rule in `requirements.md`,
  but is fixed by `design.md` (its interface table or pseudocode). Derivable from the
  docs, but it pins an interface choice rather than behaviour.
- **Implementation only**: the value appears in neither document and could only have
  been read off the code. This is the tautology case.

As a second check, every non-trivial expected value was recomputed with
`spike/verify_independent.py`, which was written from `requirements.md` alone and
shares no code with `necropsy/`. All of them agreed.

## Verdict

**No test in either file restates the implementation.** Every expected value is
either stated in `requirements.md` or `tasks.md`, or computable by hand from them.
Several values are quoted verbatim from the task text: the five `row_stride` cases,
the seven area-64 shapes and the decoder scenarios all appear in task 2.4.

Five assertions depend on design conventions rather than requirements. That's
legitimate, because `design.md` fixes them, but they test interface shape, not
behaviour. They're listed below.

The real weaknesses are **gaps and under-discriminating inputs**, not tautology.

## tests/test_closure.py

| Test | Source of expected value | Notes |
|---|---|---|
| `test_row_stride` ×5 | Spec (Req 1.1; values verbatim in task 2.4) | Hand-checkable. |
| `test_decoder_literal_and_run_mix_ok` | Spec (Req 1.9, 1.11; output length Req 4.5) | |
| `test_decoder_overrun_large_run_small_limit` | Spec for `overrun` (Req 1.10); **design convention** for `data is None` (design.md Property 6) | Req 1.10 only says output never exceeds the limit. `None` is design's encoding of that. |
| `test_decoder_trailing_marker_underrun` | Spec (Req 1.11; Req 4.5 for the truncated count) | `rle_pcx_output_length -> None` is a design convention for "skip". |
| `test_decoder_unconsumed_leftover` | Spec for `unconsumed` (Req 1.11); **design convention** for `consumed_to == 2` | Requirements never define `consumed_to` on a failure. The value 2 comes only from design.md's pseudocode. Closest thing to restating code in this file. |
| `test_decoder_consumed_to_equals_end_on_ok` | Spec (Req 1.11 "stopped exactly at data_end") | Good: uses a non-zero `start`. |
| `test_reason_degenerate_hypothesis` | Spec (Req 1.2) | **Gap:** only `width=0` is tested. `height ≤ 0`, `bit_depth ≤ 0`, `row_alignment ∉ {1,2,4}`, `header_size < 0` and `header_size > len(data)` are untested. |
| `test_reason_field_out_of_bounds` | Spec (Req 1.4) | Only the `data_end > len(data)` side. `data_end < header_size` is untested. |
| `test_reason_arithmetic_mismatch_signed` | Spec (Req 1.7 discrepancy formula) | Good: tests both signs. |
| `test_none_encoding_ok` | Spec (Req 1.3, 1.7) | `decoded == data slice` is design (Candidate carries decoded bytes). |
| `test_reason_decoder_overrun` | Spec (Req 1.12) | |
| `test_reason_decoder_underrun` | Spec (Req 1.12) | |
| `test_reason_decoder_unconsumed` | Spec (Req 1.12) | |
| `test_rle_ok_through_check_closure` | Spec (Req 1.8, 1.9) | |
| `test_reason_unsupported_encoding` | Spec (Req 1.13) | Uses `"lzw"`. The two declared-but-undecodable encodings, `rle_tga` and `tiff_compression_<n>`, aren't exercised. |
| `test_pcx_palette_trailer_applies_to_pcx_and_generic_not_tga` | Spec (Req 1.5) | The `(len(data), None)` tuple shape is design's `match_trailer` signature. **Gap:** the boundary `len(data) − 769 ≥ header_size` is untested. |
| `test_extra_registry_entry_changes_match_without_closure_edit` | Spec (Req 1.6) | Exercises `match_trailer`, not `check_closure`. That's adequate for Req 1.6 because `check_closure` delegates to `match_trailer`, but the name slightly overclaims. |
| `test_mystery_b_rle_7x7_header128_does_not_close` | Spec (Decision Record 4) | |
| `test_mystery_b_only_area_64_shapes_close` | Spec (Req 7.2 + Req 1.11) | Strongest test in the file. Req 7.2 gives a 64-byte decode at 8 bpp and alignment 1, so stride = width and closure needs `w × h = 64`. That yields exactly the seven factor pairs. Independently reproduced. Slowest test (0.58 s, 65,536 closure checks). |

## tests/test_strategies.py

| Test | Source of expected value | Notes |
|---|---|---|
| `test_strategy_names_exact` | Spec (Req 3.1) | |
| `test_inclusive_bounds_gives_8x8` | Spec (Req 3.1) | **Under-discriminating input:** bounds `(0, 0, 7, 7)` have `xmin = ymin = 0`, so a wrong implementation computing `xmax + 1` instead of `xmax − xmin + 1` passes. Needs a case with non-zero `xmin`/`ymin`. |
| `test_inclusive_bounds_without_bounds_is_empty` | Spec (Req 3.1 "applies only to hypotheses with bounds set") | Empty tuple `()` is design convention. |
| `test_rle_pcx_from_none` | Spec (Req 3.1) | |
| `test_rle_pcx_not_for_tga` | Spec (Req 3.1) | Only `tga` is checked. `pbm`, `tiff` and `generic` origins are not. |
| `test_rle_pcx_already_rle` | Spec (Req 3.1) | |
| `test_row_padding_from_1` | Spec (Req 3.1) | |
| `test_row_padding_from_4` | Spec (Req 3.1) | Starting alignment 2 (should give `[4]`) is untested. |
| `test_revision_path_extends_parent_and_parent_unchanged` | Spec for the path (Req 3.1); **design convention** for parent immutability | Immutability isn't a requirement. It follows from design's frozen dataclass + `replace`. Worth keeping. |
| `test_each_strategy_never_raises` | Spec (Req 6.4, 6.7) | Property test, 100 examples. Covers only 3 encodings, so `tiff_compression_<n>` is not generated. |

## Tests that only restate the code

None in the strict sense. The nearest case is `test_decoder_unconsumed_leftover`'s
`consumed_to == 2`, which is design pseudocode rather than a requirement. Design
conventions are also all that back `data is None` on overrun, `()` for no
candidates, the `(int, None)` trailer tuple and parent immutability.

## Other findings

1. **No property test for the closure gate or the RLE decoder exists yet.**
   Req 6.4/6.7 and design.md Property 6 require them. Task 2.5 is marked `[~]` (in
   progress) in `tasks.md`, so this is pending work, not a lost task, but the suite is
   currently green without them.
2. **`tests/__init__.py` exists.** It's an empty file, created and committed in
   `62bfee2` (Task 1.1). The report from task 2.4's agent that it was missing is
   wrong for the current tree.
3. **Correction to `spike/VERIFY.md`.** The revision-order ambiguity it reports is
   real in `requirements.md` Req 3.2, but `design.md`'s revision pseudocode settles it
   (`for h in frontier: for name, fn in STRATEGIES`, i.e. hypothesis-major). That
   order produces Req 7's paths. The fix is to state the order in Req 3.2, not to
   change behaviour.

## Full suite run

`python -m pytest tests -q` at `480b712`: **61 passed, 0 failed, 0 errors, 0 skipped,
0 warnings, 1.10 s** (1.69 s wall). Collected: `test_closure.py` 23,
`test_coherence.py` 11, `test_engine.py` 17, `test_strategies.py` 10.
