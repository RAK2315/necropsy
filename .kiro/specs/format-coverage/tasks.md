# Implementation Plan: Format Coverage

## Rules for every task

- One commit per task. The message names the task number and the requirement IDs.
- Before a task that changes behaviour: read its row in design.md, "Expected diff per task". After it: run `python -m tools.fc_diff` and put its output in the commit message. Anything outside the row stops the work and is reported.
- Every new probe, decoder and closure rule gets a Hypothesis never-raises test on `st.binary()`. Every recovered-image test compares exact pixel values. Fixtures are built in code from documented layouts.
- `python -m pytest tests -q` passes at the end of every task that is not an "Expectations" task. An "Expectations" task changes a test whose expectation is now wrong because the engine is now right, cites the requirement, and says so in its commit message.
- Windows PowerShell 5.1: `;` not `&&`. Run script files, not long inline commands.
- Develop and measure only against `spike/samples/` and `spike/samples/real/`.

## Tasks

- [x] 1. Decision Record items 28 to 32, and the diff tool
  - Append items 28 to 32 to the Decision Record of `.kiro/specs/structure-inference-engine/requirements.md`: the five principle calls, verbatim, each with its reason and the date 25 Nov 2026. Item 28 carries the wording fix of Requirement 4.4: the call stands, and the item says what a "number" is in P1 (each `0` or `1` character; whitespace between them optional; P2 and P3 still need whitespace). Add `tools/fc_diff.py` (runs the engine over the 11 samples and the 81 corpus files, compares status, termination, candidate keys and data regions with `spike/fc_baseline.json`, prints every difference) and commit the baseline taken before any engine change, with a test that the baseline equals a live run.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 20.1, 20.2_

- [x] 2. Data model: optional hypothesis fields, key, stride helper
  - `Hypothesis` gains `planes`, `row_bytes`, `ranges`, `rows_per_strip`, `tile`, `maxval`; `Candidate` gains `ranges`; `ClosureVerdict` gains `detail`; `hypothesis_key` appends the eighth element only for non-default values; `hypothesis_row_stride`; the engine passes `detail` to `RejectionEntry`; `web/serialise.py` adds keys only when non-default. Behaviour change: none. Tests: key unchanged for defaults, key differs for each new field, payload of every sample unchanged byte for byte, the whole suite and `fc_diff` show no difference.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.13, 7.14_

- [x] 3. Closure rule: samples above the declared maximum (PNM binary)
  - Add `sample_above_maxval` to `REASONS` in `necropsy/engine/types.py` and amend engine Requirement 5.6 in the same commit (Requirement 2.16; tests that assert the reason set are updated here, each cited). In `check_closure`, after the `none` length rule, when `maxval` is set: reject with `sample_above_maxval` and a detail naming offset, value and maximum when any 1-byte or big-endian 2-byte sample exceeds `maxval`. `web/serialise.py` passes the reason through; a test checks `reason` and `rejection_counts`. Tests built with `Hypothesis` objects directly (no probe yet): a sample equal to the maximum passes, one above fails, 16-bit with maxval 1000 on both bytes, never-raises on `st.binary()`.
  - _Requirements: 1.5, 2.16, 2.17, 3.9, 15.1_

- [x] 4. PNM probe, binary (P5, P6)
  - `probe_pnm` with the grammar of Requirement 3.2 to 3.7, registered in `PROBES` between `pbm` and `tiff`; `web/serialise.py` stage list gains `pnm`. Tests: crafted P5/P6 files byte by byte, with a comment, with CRLF, maxval 255 and 65535, a missing single whitespace byte, zero dimension, `P4`, `P7` and `P0` not matched, never-raises. Engine tests: exact status, key, header size, data region and decoded bytes. Expected diff: 9 files (design.md, row 4).
  - _Requirements: 1.5, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 15.1_

- [x] 5. Render PNM grey and RGB, 8 and 16 bit
  - `web/pixels.py` renders PNM 8, 16, 24 and 48-bit samples scaled by `maxval`; `web/serialise.py` passes `maxval`. Tests: exact pixel values for P5 and P6 fixtures including maxval 15 and 65535.
  - _Requirements: 16.1, 16.3, 16.4, 16.5_

- [x] 6. Decoder: `pnm_text`
  - `necropsy/engine/decoders.py` with `DecodeResult` (six states: `ok`, `overrun`, `underrun`, `unconsumed`, `malformed`, `above_maxval`) and `pnm_text_decode`. Tests for every state and every `consumed_to` of Requirement 4.7 to 4.11: P1 as digit runs with no separators (ok), P1 mixed with separators and comments (ok), a P1 digit `2` (`above_maxval`), a P1 letter (`malformed`), a P2 number above maxval (`above_maxval`), `255255` in P2 (`above_maxval`), a P2 non-digit token (`malformed`), a short file (`underrun`), an extra digit or number (`unconsumed`), the packing of P1 rows, 16-bit output, a 6-digit token with leading zeros, never-raises, no allocation above `max_output_bytes`.
  - _Requirements: 2.7, 2.8, 2.9, 2.10, 2.11, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 15.1_

- [x] 7. Closure rule: decoder dispatch and the decode cap
  - `DECODERS` table and `DECODE_CAP` in `decoders.py`; `check_closure` dispatches on it, carries `detail`, and rejects above the cap with `degenerate_hypothesis`. `decoder_malformed` is added to `REASONS` and engine Requirement 5.6 is amended again (Requirement 2.16). `pnm_text` is the first entry. Tests: dispatch of every state to its reason (`overrun`, `underrun`, `unconsumed`, `malformed`, `above_maxval` to `decoder_overrun`, `decoder_underrun`, `decoder_unconsumed`, `decoder_malformed`, `sample_above_maxval`), both new reasons pass through `web/serialise.py` unchanged, cap boundary (exactly the cap passes, one above is rejected), unknown encoding still `unsupported_encoding`, never-raises.
  - _Requirements: 2.12, 2.13, 2.16, 2.17, 4.12, 15.1_

- [x] 8. PNM probe, text (P1, P2, P3)
  - Extend `probe_pnm` with Requirement 4.1 and 4.2. Tests: crafted files for each magic, the exact-count rule (one number short, one too many), a number above maxval, comments, P1 as digit runs and as separated digits (both resolve with identical pixels), a P1 with a letter (fails with `decoder_malformed`), P2 with no whitespace between numbers (fails), a P3 with 16-bit maxval. Expected diff: 4 files (design.md, row 8), including `pillow_hopper_1bit_plain.pbm`.
  - _Requirements: 1.1, 4.1, 4.2, 4.4, 4.13, 15.1_

- [x] 9. Render plain-text PNM
  - P1 renders as a 1-bit black-is-one image through the PBM path. Tests: exact pixels for P1, P2, P3 fixtures after a full engine run.
  - _Requirements: 16.1, 16.4_

- [x] 10. Decoder: `rle_tga`
  - `rle_tga_decode` with Requirement 5.2 to 5.7. Tests: run packet, raw packet, a packet across a row end (must decode), overrun without writing, region ending inside a packet, leftover byte, 8, 16, 24 and 32-bit pixels, never-raises, no allocation above the bound.
  - _Requirements: 1.3, 2.7, 2.8, 2.9, 2.10, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 15.1_

- [x] 11. Closure rule: register `rle_tga`
  - Add `rle_tga` to `DECODERS` with `pixel_bytes = ceil(bit_depth / 8)`; it uses the trailer registry's `data_end`. Tests: crafted RLE TGA with and without a TGA 2.0 footer and extension area, exact pixels in stored order and through the renderer. Expected diff: 6 files (design.md, row 11; first predicted 7, corrected in Task 12).
  - _Requirements: 1.3, 5.1, 5.8, 5.9, 5.10, 16.1, 16.4_

- [x] 12. Expectations: RLE TGA is now decoded
  - Change the tests whose expectation the engine now contradicts: engine Requirement 7.17 test (`pillow_rgb32rle.tga` not RESOLVED), the `rle_tga` row of the `unsupported_encoding` parametrisation in `tests/test_closure.py`, and any real-corpus expectation for the six files, and `pillow_cross_scan_line.tga` as an open in-scope failure. Each change cites Requirement 5.9; the commit message says so and lists each test.
  - _Requirements: 5.9, 20.4_

- [x] 13. Closure rule: declared row bytes and planes
  - `hypothesis_row_stride` used by every stride site; `check_closure` applies Requirement 6.3 and 6.4. Tests built with `Hypothesis` objects: `row_bytes` replaces the derived stride, `row_alignment` is ignored, `bit_depth % planes`, `bytes_per_line` too small, an RLE planar region, never-raises.
  - _Requirements: 6.3, 6.4, 6.7, 15.1_

- [x] 14. Strategy guard: no padding variants for declared row bytes
  - `row_padding_variants` returns no candidate when `row_bytes` is set. Tests: guarded and unguarded cases, the other two strategies unchanged, single-plane results unchanged, never-raises.
  - _Requirements: 6.5, 6.8, 15.1_

- [x] 15. PCX probe: multi-plane seed
  - Set `planes`, `row_bytes` and `bit_depth` when `planes > 1`. Tests: crafted 3-plane RLE and 4-plane 1-bit PCX files, exact decoded scanlines, path `["inclusive_bounds"]`, single-plane results unchanged, `bytes_per_line` 0, never-raises. Expected diff: 3 files (design.md, row 15).
  - _Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 15.1_

- [x] 16. Render multi-plane PCX
  - Planar scanlines to RGB (3 or 4 planes of 8 bits) and to the header palette (planes of 1 bit); a reason for other layouts. `web/serialise.py` passes the header palette. Tests: exact pixels for both, one `RenderFailure` case.
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 17. Closure rule: several data ranges, strips
  - Requirements 7.5 to 7.8, 7.10 to 7.12 for strips and `none`. Tests with `Hypothesis` objects: concatenation, a last strip with fewer rows, one range short, one range long, a range out of bounds, a range over a header field (Requirement 12 per range), a field between two ranges (accepted), overlapping ranges, wrong strip count, never-raises, no allocation sized from the declared count.
  - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.10, 7.11, 7.12, 15.1, 15.5_

- [x] 18. TIFF probe: strip arrays
  - Requirement 8 in full. Tests: crafted TIFFs with inline and offset arrays, SHORT and LONG, both byte orders, default `RowsPerStrip`, last strip with remaining rows, count mismatches, both strips and tiles present, an array past the file end, count above `TIFF_MAX_RANGES`, single-strip results unchanged, never-raises. Engine tests with exact pixels. Expected diff: 6 files (design.md, row 18).
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 15.1, 15.5_

- [x] 19. Render 12-bit and 16-bit grey
  - TIFF and PNM 12-bit and 16-bit grey in the declared byte order; a `RenderFailure` naming the layout for 16-bit RGB TIFF. `web/serialise.py` passes the byte order from the `byte_order` field. Tests: exact values for both byte orders and for 12-bit packing.
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 20. Closure rule: tile assembly
  - Requirements 7.9 and 7.12 for tiles. Tests with `Hypothesis` objects: a tile grid with a partial last column and last row, every assembled byte compared, tile width not byte aligned (rejected), wrong tile count, 1-bit and 24-bit tiles, never-raises, the assembled size checked against the cap first.
  - _Requirements: 7.9, 7.12, 9.6, 15.1_

- [x] 21. TIFF probe: tiles
  - Requirement 9. Tests: crafted tiled TIFFs, missing tag 322, 323 or 325, unequal counts, 273 and 324 both present, neither present, tile order and position, never-raises. Engine test with exact assembled pixels. Expected diff: 1 file (design.md, row 21).
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 15.1_

- [x] 22. TIFF probe: Predictor refusal
  - Requirement 10. Tests: Predictor 2 over compression 1, 5 and 8, Predictor 1 and absent unchanged, an unreadable tag 317, the detail names tag and value, the closure gate never decodes it, the four corpus files. Expected diff: none in status (design.md, row 22).
  - _Requirements: 1.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 15.1_

- [x] 23. Decoder and registration: PackBits
  - `packbits_decode` and its `DECODERS` entry for 32773. Tests: every state, the `0x80` no-op inside the stream and as a leftover byte, padded strip fails, never-raises, bomb allocation test; engine test on a crafted multi-strip PackBits TIFF with exact pixels. Expected diff: 1 file (design.md, row 23).
  - _Requirements: 1.2, 2.7, 2.8, 2.9, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 15.1, 15.4_

- [x] 24. Decoder and registration: LZW
  - `lzw_tiff_decode` and its entry for 5. Tests from a documented encoder in the test file, covering every case in Requirement 12.12, the width changes at 511, 1023 and 2047, a full table, the worst-case expansion stream within 2 seconds (Requirement 15.3), never-raises; engine test on a crafted LZW TIFF. Expected diff: 2 files (design.md, row 24).
  - _Requirements: 1.2, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 15.1, 15.3, 15.4_

- [x] 25. Decoder and registration: Deflate
  - `deflate_zlib_decode` and entries for 8 and 32946. Tests: every state, a corrupt checksum, trailing bytes, a zlib bomb bounded by `max_output_bytes + 1`, never-raises; engine test on a crafted TIFF. Expected diff: 3 files (design.md, row 25); `libtiff_deflate-last-strip-extra-data.tiff` stays FAILED.
  - _Requirements: 1.2, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 15.1, 15.4_

- [x] 26. Decoder and registration: LZMA
  - `lzma_xz_decode` and its entry for 34925. Tests: every state, a stream with a dictionary above the memory limit, a bomb, never-raises; engine test on a crafted TIFF. Expected diff: 1 file (design.md, row 26).
  - _Requirements: 1.2, 14.1, 14.2, 14.3, 14.4, 15.1, 15.4_

- [x] 27. Refusals and the standard-library rule
  - Tests: CCITT 2, 3, 4, old-style JPEG 6, JPEG 7, SGILog 34676, ZSTD 50000 and WebP 50001 headers are `FAILED` with `unsupported_encoding` naming the code; planar configuration 2 refused; a BMP header gets no seed from any probe; every module under `necropsy/engine/` imports only the standard library.
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

- [x] 28. Expectations: TIFF layouts now decoded
  - Change every existing test whose expectation the TIFF work now contradicts (for example corpus expectations for LZW, Deflate, PackBits, multi-strip and tiled files; the "only single-strip TIFF is in scope" wording in tests). Each cites the requirement that makes it wrong; the commit message lists them.
  - _Requirements: 8.11, 9.6, 11.1, 12.1, 13.1, 14.1, 20.4_

- [x] 29. Emission: multi-plane PCX
  - `necropsy/emit/layout.py` emits `image.row_bytes` and the planes `bit_depth` for `planes > 1`; `render.py` states the planar scanline in EARS; the reference reader applies `row_bytes`. A single-plane PCX spec is byte for byte unchanged. Test: the emitted spec for a crafted 3-plane PCX passes plain pytest with the reference reader.
  - _Requirements: 17.4, 17.8, 17.9_

- [x] 30. Emission: `rle_tga`
  - TGA mapping sends 9, 10, 11 to `rle_tga`; EARS definition of `rle_tga` from Requirement 5; the reference reader decodes it from that text. Test: the emitted spec for `pillow_200x32_rgb_tl_rle.tga` passes plain pytest.
  - _Requirements: 17.1, 17.2, 17.8, 17.9_

- [x] 31. Expectations: emitted TGA specs now name `rle_tga`
  - Change `tests/test_encoding_definitions.py` (no emitted spec names `rle_tga`; mystery_c mapping) and any emission test that pins the old TGA mapping. Cite Requirement 17.2, which replaces engine Requirement 9.29 for 9, 10 and 11.
  - _Requirements: 17.2, 20.4_
  - Folded into Task 30 (commit e0eeab8).

- [x] 32. Emission: PNM
  - `pnm` layouts of kind `file`, `image.maxval`, header grammar in prose, `pnm_text` defined when used; reference reader decodes `pnm_text` and reads P5/P6 rasters. Tests: emitted specs for a P5, a P6 and a P3 pass plain pytest.
  - _Requirements: 17.1, 17.5, 17.8, 17.9_

- [x] 33. Emission: TIFF compression mapping, predictor entry, decoders
  - Widen the compression mapping; add the `predictor` entry with `expect: 1`; EARS definitions for `packbits`, `lzw_tiff`, `deflate_zlib` and `lzma_xz`; reference reader implements them (`zlib`, `lzma` from the standard library). Test: emitted specs for a PackBits, an LZW, a Deflate and an LZMA TIFF pass plain pytest.
  - _Requirements: 17.1, 17.3, 17.8, 17.9_

- [x] 34. Expectations: emitted TIFF specs
  - Change the emission tests that pin the old TIFF mapping (`{"1": "none"}`, `otherwise: unsupported`) and the tag table without `predictor`. Cite Requirement 17.3; list each test in the commit message.
  - _Requirements: 17.3, 20.4_

- [x] 35. Emission: several data ranges
  - `data.ranges`, `image.rows_per_strip`, `image.tile` in `file` layouts; reference reader assembles strips and tiles. Tests: emitted specs for a multi-strip TIFF and a tiled TIFF pass plain pytest; assembled bytes equal the engine's.
  - _Requirements: 17.6, 17.8, 17.9_

- [x] 36. Emission: tests, break check, unchanged-spec check, validation
  - Emitted `test_<module>.py` requires a successful decode for every decodable encoding with no skip or `refused` clause except source-too-large; `tools/break_check.py` fails a do-nothing parser on each new layout; a test compares every emitted spec of the samples and the corpus with today's and allows only the differences of Requirement 17.2 and 17.3; the emitted specs of the new layouts pass Kiro's format validation.
  - _Requirements: 17.7, 17.10, 17.11, 17.12_

- [x] 37. Scope: rules, script, manifest, README
  - `tools/scope_from_headers.py` rewrites `scope` and `scope_reason` in `spike/samples/real/manifest.json` from header bytes; `spike/samples/real/README.md` scope rules and counts rewritten; a test that the manifest equals the script and every SHA-256 is unchanged. Expected diff: 38 files change from out to in (39 in all with `pillow_cross_scan_line.tga`, set in scope in Task 12), none from in to out (design.md).
  - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

- [x] 38. Corpus comparer
  - Extend `tools/real_corpus.py`'s canonical forms to every newly resolved layout (Requirement 19.2). Test the comparer on crafted fixtures against Pillow where Pillow is installed.
  - _Requirements: 19.2, 19.3_

- [x] 39. Regenerate the results
  - Run `python -m tools.real_corpus`. Commit `docs/REAL-CORPUS-RESULTS.md` and `spike/real_corpus_results.json`. Add the expected open failure (`libtiff_deflate-last-strip-extra-data.tiff`) to `OPEN_IN_SCOPE_FAILURES` as a strict expected failure with a measured note, and any other in-scope valid file that measures FAILED; change the "five of six invalid files fail" test in its own commit if `goimage_invalid-palette-ref.tiff` is `RESOLVED`, citing Requirement 19.5; write every mismatch and its cause into the notes; write measured counts into design.md beside the predicted ones, and into the repository README and `.kiro/specs/real-corpus/design.md`.
  - _Requirements: 19.1, 19.3, 19.4, 19.5, 19.6, 20.2_

- [x] 40. Verification and report
  - `python -m pytest tests -q`, `node --test tests/ui/js/logic.test.mjs tests/ui/js/screens.test.mjs`, `python -m tools.fc_diff` against the baseline (every difference accounted for by a task row), `git diff` shows nothing under `public/`. Report predicted against measured, every mismatch, and every open failure.
  - _Requirements: 19.6, 20.2, 20.4, 20.7, 20.8_
