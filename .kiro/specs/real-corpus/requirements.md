# Requirements Document

## Introduction

This spec measures the engine on files it did not write and nobody here wrote. `spike/samples/real/` holds 81 files from six upstream decoder test suites (PCX, TGA, TIFF, PBM/PGM/PPM), each pinned to a commit, with a manifest recording source, licence, format, stated scope and what Pillow 12.2.0 does with each file.

The test is differential: run the engine over every file, compare recovered pixels with Pillow's where both produce pixels, and record every refusal with its reason. A table with every row green would mean the files were chosen to be easy. This spec expects failures and reports them as measured.

The engine, the closure gate and the corpus manifest are not changed by this spec. The engine spec `structure-inference-engine` is closed. Fixing anything this spec exposes is a separate decision.

## Glossary

- **Corpus**: the 81 files in `spike/samples/real/`, listed in its `manifest.json`.
- **Scope**: whether a file is inside the engine's stated scope. The manifest assigns it from header bytes. Decision 3 in design.md reclassifies one file.
- **Invalid by construction**: the six files the corpus README records as fuzzer, overrun or regression inputs that Pillow is right to refuse.
- **Canonical pixels**: a form that both sides are converted to before comparison: rows top to bottom, channels in R, G, B, A order (grey and alpha as L, A; palette images as indices), row padding cropped, 1-bit images as one byte per pixel with 1 meaning white, TGA 16-bit colour as four bytes of 5, 5, 5 and 1 bits.
- **Literal reading**: a result that states what the bytes arithmetically admit, with no claim that the file is a valid image of any format.
- **Results table**: `docs/REAL-CORPUS-RESULTS.md`, generated from `spike/real_corpus_results.json`.

## Requirements

### Requirement 1: Run the engine over the whole corpus

**User Story:** As the builder, I want the engine's result on every real file recorded, so that claims about it rest on files I did not write.

#### Acceptance Criteria

1. THE runner SHALL run the engine over all 81 files, with no file skipped or removed.
2. THE runner SHALL record per file: status, termination, number of checks, and for each candidate its width, height, bit depth, header size, row alignment, encoding, probe, revision path and data region.
3. THE test SHALL verify that every corpus file matches the SHA-256 in the manifest.
4. THE test SHALL verify that the committed results equal a live engine run, file by file, so the table cannot drift from the engine.

### Requirement 2: Pixel comparison with Pillow

**User Story:** As the builder, I want recovered pixels compared with an independent decoder, so that "recovered" means the right pixels.

#### Acceptance Criteria

1. FOR EACH in-scope valid file that the engine RESOLVES and Pillow decodes, THE runner SHALL compare canonical pixels byte for byte.
2. THE comparison SHALL account for row order (TGA descriptor bit 5) and channel order (TGA B, G, R to R, G, B), and SHALL crop row padding.
3. THE runner SHALL record the SHA-256 of Pillow's canonical pixels, so that the test needs no Pillow in CI.
4. WHEN Pillow is installed, THE test SHALL check the committed hashes against a live Pillow decode.
5. A mismatch SHALL be recorded as a mismatch. The comparison SHALL NOT be changed to remove it.
6. THE comparison SHALL NOT interpret channel semantics that the engine does not interpret. A difference that arises only from such semantics SHALL be recorded as a known interpretation difference and stated under Limits in design.md.

### Requirement 3: Refusals

**User Story:** As the builder, I want out-of-scope files refused with a stated reason, so that the table shows where the engine stops.

#### Acceptance Criteria

1. FOR EACH out-of-scope file, THE test SHALL assert status FAILED, and the termination SHALL be recorded (`exhausted` or `no_hypothesis_checked`).
2. THE one exception is `pillow_ossfuzz-4836216264589312.pcx`, covered by Requirement 4.

### Requirement 4: Invalid by construction

**User Story:** As the builder, I want to know whether the engine accepts garbage, so that I describe the engine's tolerance accurately.

#### Acceptance Criteria

1. OF THE six invalid-by-construction files, THE engine SHALL return FAILED for five.
2. FOR `pillow_ossfuzz-4836216264589312.pcx`, THE engine SHALL return RESOLVED with width 2, height 1, bit depth 1, header size 128, no encoding, data region [128, 129), from Generic Search.
3. THE PCX probe SHALL NOT have matched that file (its encoding byte is `0x20`), so no `probe_precondition_failed` is recorded and the rejection list is empty.
4. THE spec emitted for that result SHALL have layout kind `file` and SHALL say it describes this one file only. It SHALL make no PCX claim.
5. THE results table SHALL state that this result is a literal reading and not a recovery claim.
6. THE engine SHALL NOT be given a header-size-to-file-size threshold to refuse this file. Such a threshold is the heuristic gate that coherence scoring was deleted for.

### Requirement 5: The results table

**User Story:** As a judge or reader, I want one table of what happened on real files, so that I can see recoveries and refusals together.

#### Acceptance Criteria

1. THE table SHALL have one row per corpus file with: file, format, scope, our status (with termination for FAILED), Pillow's result, whether pixels match, and a note.
2. THE table SHALL be generated by `python -m tools.real_corpus` and committed.
3. THE table SHALL show the five in-scope failures as measured, marked open, with no change to their rows.
4. THE table SHALL show `pillow_rgba16.tga` as a mismatch with the known interpretation difference stated.
5. THE table SHALL show the scope reclassification of `libtiff_test_ifd_loop_to_self.tif`.

### Requirement 6: Open failures stay visible

**User Story:** As the builder, I want unfixed failures to stay visible in the test suite, so that they are neither hidden nor mistaken for passes.

#### Acceptance Criteria

1. THE five in-scope valid files that FAIL SHALL be strict expected failures in the test suite, with the expectation unchanged: in scope means RESOLVED.
2. WHEN one of them is fixed, THE strict expected failure SHALL turn into a test error, which is the cue to regenerate the table and remove the marker.
3. THIS spec SHALL NOT investigate or fix them.
