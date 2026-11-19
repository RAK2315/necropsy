# Implementation Plan: NECROPSY UI

## Overview

Build the web layer over the finished engine. Order: skeleton and early deploy (so the host gate clock starts), pixel decoder, serialiser, external samples, then the frontend screens, then replay, spec panel and polish. Frontend tasks are checked by looking at them, so each lists what must be visible.

Do not start task 1 until the user confirms that the engine amendments (including the `image_descriptor` `FieldRecord` at offset `0x11` of a TGA seed) are committed.

Rules for every task:
- Do not modify anything under `necropsy/`. If the engine's interface differs from its `design.md`, stop and report.
- Commit after every completed task.
- Shell is Windows PowerShell 5.1: `;` between statements, never `&&`. Run tests with `python -m pytest tests/ui -q`.
- Expected pixel values come from `spike/make_samples.py` ground truth, not from the decoder.
- No framework, no third-party requests, no feature beyond requirements.md.
- Every Python function in `web/` and `api/` returns a structured value and never raises on any input.

## Tasks

- [x] 1. Skeleton
  - Create `app.py` (repo root) with `POST /api/analyze` (65,536 cap, 413, engine call, `engine_ms`, minimal JSON of `status` and `total_checks`), a one-page `public/index.html`, `requirements.txt` with `fastapi`.
  - Test with `TestClient`: 413 over cap, 200 on empty body, 200 on `mystery_a`.
  - _Requirements: 1.1 to 1.9, 14.7_

- [x] 2. Deploy the skeleton and start the idle clock
  - Deploy to Vercel Hobby as the project `necropsy` and as the canary `necropsy-coldtest`. Confirm the page loads and a sample returns a real engine result on `necropsy`. Write both URLs and the canary's deploy time into `docs/KIRO-LOG.md`.
  - Add `tools/cold_hit.ps1` that times the first-screen request and an analyse request.
  - **Host gate canary.** The Requirement 14 gate is measured against a second project, `necropsy-coldtest`, deployed once from this same skeleton and never requested or redeployed afterwards. The main project `necropsy` is hit constantly by tasks 3 to 14, so its idle timer never runs. Nothing may request the `necropsy-coldtest` URL until the cold test in task 15. If the two projects diverge enough that the canary stops being representative (for example the main project changes runtime, dependencies, region or plan), the gate SHALL be re-run on a fresh untouched copy deployed from the then-current code, and its 24-hour clock restarted.
  - Continue with tasks 3 onward meanwhile, deploying and testing against `necropsy` freely. Deploy by day 10 of the build.
  - _Requirements: 14.1, 14.2, 14.6, 14.7_

- [x] 3. Pixel decoder
  - Create `web/pixels.py` as in design.md, including the palette path.
  - Tests: golden pixels for `mystery_a`, `b`, `c`, `e`, `h`, `i` per Requirement 3.14 (palette for `b` and `i`, BGR for `c`, padding for `h`, PBM polarity for `a`), synthetic bottom-left buffer flips and says so, a record that is not a one-element integer tuple is ignored, synthetic 4-bit with odd width and padding, synthetic 32-bit, short palette gives greyscale, 16-bit gives the failure reason, inconsistent geometry gives its reason. Hypothesis test: never raises on arbitrary bytes and geometry.
  - _Requirements: 3.1 to 3.15_

- [ ] 4. Serialiser and spec zip
  - Create `web/serialise.py` and `web/speczip.py`. Add `POST /api/spec.zip`. Extend `/api/analyze` to return the full payload.
  - Implement the pixel budget, the 4,000,000-byte size budget with `rejections_omitted` and `rejection_counts`, and the palette read.
  - Tests: status for all nine corpus files per the engine spec; `mystery_i` assertions from Requirement 15.5; candidate order equals discovery order for `d`, `f`, `g`; zip holds `<slug>/` with exactly three files equal to the `emit_spec` text; sample and renamed bytes give identical payloads; Hypothesis test on the endpoint (200 and valid JSON). Add a test that forces the size budget with a large rejection list.
  - _Requirements: 1, 2, 12.4 to 12.8, 15.3 to 15.6_

- [ ] 5. External samples
  - `pip install pillow` into the dev environment only (`requirements-dev.txt`, not `requirements.txt`). Never write the sample bytes by hand.
  - Write `tools/make_external_samples.py`: it generates a 64 × 48 source image with at most 256 colours, writes `spike/samples/external/source.ppm`, and calls Pillow to write `external_a` (mode `P`, PCX) and `external_b` (mode `RGB`, TGA, no compression, bottom-left origin). The size is fixed now and is not changed after the engine is run. Commit the outputs unmodified.
  - Write `spike/samples/external/README.md` with the Pillow version, Python version, the exact `save` calls, the source image and script, date, the TGA descriptor byte as written, and the statement that Pillow's encoders wrote the bytes, not this project's code. Link it from the top-level `README.md`.
  - Run the engine on both with no change. Add serialiser tests per Requirement 11.15 and 11.16 (exact pixels against the source PPM, no flip in the test, `external_b` note states the flip). If either does not return RESOLVED, stop and report the engine's output as a finding. Change nothing to make it pass: not the engine, the sample, the size, the `save` arguments or the expectations.
  - _Requirements: 11.13 to 11.16, 15.4_

- [ ] 6. Frontend shell and samples
  - `tools/copy_samples.py` copies `spike/samples/` and `spike/samples/external/` into `public/samples/` and writes `samples/index.json`. A test asserts byte-identity.
  - Build the drop zone, file picker, size refusal, the `Analysing…` state, the sample list with name, size and download, provenance line on external samples, and the one-line scope statement.
  - Must be visible: near-empty first screen, one instruction, samples below, clicking `mystery_a` posts bytes and logs the status.
  - _Requirements: 11.1 to 11.12, 13.1 to 13.3, 13.7_

- [ ] 7. Pure logic with tests
  - `public/js/logic.js` as in design.md. `node --test` tests for `fieldRange`, `regions`, `byteRoles` (overlap, `mystery_f` equivalent reads), `buildSteps` (payload order, nothing added), `batch` (10 s bound, exact ranges), `stageOf`, `revisionDiffs`, `declaredVsActual`.
  - _Requirements: 5.4 to 5.8, 7.2, 7.6, 7.7, 8.6 to 8.8, 15.8_

- [ ] 8. Static hex pane and field table
  - Virtual-scrolled pane with offset, hex and ASCII columns, grey undecoded bytes, accent field bytes, region gutter labels, trailer marker, field labels on hover or focus, two-way highlight with the field table, keyboard access.
  - Must be visible: `mystery_e` shows header, data region and labelled fields; `mystery_b` shows the `pcx_palette_256` trailer; a 65,536-byte file scrolls smoothly.
  - _Requirements: 5, 6_

- [ ] 9. RESOLVED screen and image
  - Canvas drawing at the largest integer scale in an accent-bordered frame, render note, dimensions, row-by-row reveal under 2 seconds, closure line, trailer, revision path, alternative paths, revision diffs, declared versus actual pair.
  - Must be visible: `mystery_b` in palette colours; `mystery_c` in correct colours; `mystery_h` 6×6 with no padding column; `mystery_i` shows `declared: none (byte 0x02 = 0x00)` and `actual: rle_pcx` without scrolling at 1280×720; the external samples render.
  - _Requirements: 4, 8_

- [ ] 10. UNRESOLVED_AMBIGUITY screen
  - Leading statement, identical cards in a wrapping grid in payload order, common frame, coherence in one fixed place, union hex pane with hover to show a candidate, no selection on load, 16-bit placeholder card in the same frame as an image.
  - Add the neutrality test: two fixtures differing only in coherence render identical markup apart from the coherence text.
  - Must be visible: `mystery_d`, `mystery_f` and `mystery_g` show every candidate with its image, none preferred, success styling.
  - _Requirements: 9, 4.2_

- [ ] 11. FAILED screen
  - Chip, termination sentence, counts, grouped collapsible rejections with the 200 cap, omitted-rejection notice, partial candidates heading.
  - Must be visible: a text file and an empty file each give a complete FAILED screen, distinct from the two success screens.
  - _Requirements: 10, 11.9_

- [ ] 12. Spec panel and download
  - Tabs for the three files, folder name, framing sentence, download button using `/api/spec.zip`, the `EmitError` message for FAILED.
  - Must be visible: the emitted `requirements.md` for a recovered file within 20 seconds of the first screen; the downloaded zip opens with one folder and three files.
  - _Requirements: 12_

- [ ] 13. Replay
  - Controller over `buildSteps` and `batch`: play, pause, step, skip to end, 0.5× to 4×, `Replay` label with the `engine_ms` sentence, exact counter, step log, lit fields per step, reads-in-file-order note, reduced-motion start at the end.
  - Must be visible: `mystery_i` replays the seed rejection, the intermediate rejection and the resolved candidate in order; a large generic failure replays within 10 seconds at 1× with an exact range counter.
  - _Requirements: 7_

- [ ] 14. Polish pass
  - One pass over the visual language at 1280×720: type scale, spacing, the accent used only on recovered data, status chips, region labels, focus rings, reduced motion. Check no scanlines, glow or third-party request.
  - Must be visible: each screen looks finished, and none uses the accent on anything other than recovered data.
  - _Requirements: 13_

- [ ] 15. Host gate
  - At least 24 hours after task 2, run `tools/cold_hit.ps1` against the deployed URL. Record the date, the idle time, the first-screen time and the cold analyse time in `docs/KIRO-LOG.md`, and read the plan's current terms.
  - If the cold analyse time is over 5 seconds or the terms fail, stop and ask the user to choose a new host now. Do not continue UI work on a failed host.
  - _Requirements: 14.2 to 14.4_

- [ ] 16. Final deploy and acceptance
  - Redeploy, run each Requirement 13.5 beat on the public URL at 1280×720, record a screen capture and time for each. Schedule the 15 December and weekly cold-hit checks in `docs/KIRO-LOG.md`.
  - _Requirements: 13.5, 14.5, 15.7_
