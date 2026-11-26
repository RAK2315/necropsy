# Design Document

## Overview

- `tools/real_corpus.py`: runs the engine over the corpus, converts both sides to canonical pixels, writes `spike/real_corpus_results.json` and `docs/REAL-CORPUS-RESULTS.md`. Run `python -m tools.real_corpus`. It needs Pillow.
- `tests/test_real_corpus.py`: asserts the expectations below, and that the committed results equal a live run. It runs without Pillow. With Pillow it also checks the committed Pillow hashes.

Nothing under `necropsy/` or `spike/samples/real/` is changed.

## Results as measured

Engine over all 81 files, default 5 s deadline. No run hit the deadline. No result was ambiguous. The most checks on any file was 6.

| Group | Files | Our status |
|---|---:|---|
| In scope, valid, pixels equal Pillow's | 54 | RESOLVED, match (49) or equal after WhiteIsZero inversion (5) |
| In scope, valid, documented verdict | 4 | RESOLVED, 16-bit and 12-bit scaling, rgb32rle alpha |
| In scope, valid, known interpretation difference | 1 | RESOLVED, alpha bit differs (`pillow_rgba16.tga`) |
| In scope, valid, open failure | 2 | FAILED (`exhausted`): `pillow_cross_scan_line.tga`, `libtiff_deflate-last-strip-extra-data.tiff` |
| In scope, invalid by construction | 4 | 3 FAILED (`exhausted`), 1 RESOLVED (`goimage_invalid-palette-ref.tiff`, Pillow refuses it) |
| Out of scope | 15 | FAILED: 14 `exhausted`, 1 `no_hypothesis_checked` |
| Out of scope, invalid by construction | 1 | RESOLVED, literal reading (`pillow_ossfuzz-4836216264589312.pcx`) |
| **Total** | **81** | 61 RESOLVED, 20 FAILED |

This table is the state after format-coverage Task 39. Before that spec the table read 23 / 1 / 2 / 54 / 1, 25 RESOLVED and 56 FAILED, with 26 files in scope and 55 out (Decision 3). In scope is now 65 files and out of scope 16, as `tools/scope_from_headers.py` writes them from header bytes. All counts above were checked against `docs/REAL-CORPUS-RESULTS.md` row by row. The table with every file is `docs/REAL-CORPUS-RESULTS.md`.

The 14 `no_hypothesis_checked` refusals are all PNM files: every PNM file except the five binary PBM (`P4`) files. The 40 `exhausted` refusals are the TIFF, TGA and PCX files outside the stated scope (compression, RLE TGA, several strips, tiles, planar, several PCX planes) and the invalid ones. The reason for each is in the table's note column, taken from the manifest's scope reason.

## Decisions

These were made by the builder after the first measurement. They are recorded so they are not reopened by a later reading of the table.

1. **`pillow_ossfuzz-4836216264589312.pcx` RESOLVING is correct.** The file is 129 bytes and starts with the PCX signature. Its encoding byte (offset `0x02`) is `0x20`, which has no reading in PCX, so the PCX probe declines under engine Requirement 2.10: it records one `probe_precondition_failed` (source `pcx`, no hypothesis) and emits no seed. Generic Search then finds that 129 bytes admit a 128-byte header plus one data byte: a 2×1, 1-bit image. That is the method being literal. It is not a recovery claim, and the emitted spec has layout kind `file` and says it describes this one file only, because the result's source is Generic Search. `test_ossfuzz_resolves_with_a_literal_reading_and_a_file_layout_spec` asserts the result, the one rejection entry and the emitted layout kind.

2. **`pillow_rgba16.tga` is a known interpretation difference, not a recovery error.** The file declares 16-bit pixels. Our 16-bit words agree with Pillow's: the three 5-bit colour values are equal. Pillow expands bit 15 as alpha with set meaning transparent, and the engine returns raw words and interprets no channel semantics, so the alpha bit differs in both pixels. The row stays a mismatch in the table, with the note. The comparison is not changed to hide it. `test_rgba16_differs_only_in_the_alpha_interpretation` asserts that colour bits are equal and the alpha bit differs.

3. **`libtiff_test_ifd_loop_to_self.tif` is in scope.** The file's IFD chain loops, which does not prevent the first IFD being read, and the engine recovers 20×20, 8-bit pixels that match Pillow. The manifest records it as in scope. Scope has one source of truth, the manifest; the tool applies no override in code.

4. **All five in-scope failures were fixed by the engine.** `goimage_no_compress.tiff`, `goimage_no_rps.tiff`, `goimage_video-001-uncompressed.tiff` and `sdlimage_sample.tif` were in scope, valid, decodable by Pillow, and FAILED with `exhausted`. The engine's Decision Record item 20 (the TIFF probe reads the BitsPerSample array) fixed them: all four now RESOLVE through the TIFF probe and their pixels match Pillow's. `pillow_p_16.tga` was in scope, valid, decodable by Pillow, and FAILED with `exhausted`, because the engine ended its data region at the TGA 2.0 footer and did not read the offsets the footer and extension area declare. The engine's Decision Record item 22 fixed it: it now RESOLVES through the TGA probe with data region [560, 16944), and its pixels match Pillow's. No in-scope valid file is an open failure; `OPEN_IN_SCOPE_FAILURES` is empty, and the strict expected-failure mechanism (Requirement 6) stays for any future entry.

## Comparison

`ours_canonical` and `pillow_canonical` convert to the canonical form in the Glossary.

| Format | Ours | Pillow |
|---|---|---|
| TGA | rows reversed when descriptor (`0x11`) bit 5 is clear; 24 and 32 bit B, G, R(, A) to R, G, B(, A); 16-bit type 3 as L, A; 16-bit colour as 5, 5, 5, 1 bits | Pillow orients rows itself; 16-bit RGBA reduced to 5 bits per colour and an alpha flag |
| PCX | row stride cropped to `ceil(width × bit_depth / 8)`; 1-bit: set bit is white | mode `1`, `L` or `P` |
| TIFF | 1-bit: set bit is white unless PhotometricInterpretation is 0; 24 and 32 bit as stored | mode `1`, `RGB`, `RGBA` |
| PNM (P4) | 1-bit: set bit is black | mode `1` |

Palette images are compared as indices. Palettes are not recovered or compared.

## Limits

- **Alpha in 16-bit TGA.** The engine returns raw words. Pillow interprets bit 15 as alpha. See Decision 2.
- **Palettes.** The engine recovers no palette semantics (the UI reads the 769-byte PCX trailer separately). Palette images are compared as index bytes, so a wrong palette would not be seen here.
- **The comparer handles the formats listed above.** A recovered result in a form it does not handle is recorded as "not comparable" with the reason, and is not counted as a match. None of the 81 files hit this path.
- **Pillow is one reference.** A byte match shows that two independent readings agree, not that either is right. The files carry no other ground truth.
- **Scope is the builder's stated scope.** The manifest assigns it from header bytes, and Decision 3 records the one assignment that was corrected. Files outside it were included on purpose, so the refusals are visible.
- **The corpus is one pass over six test suites.** It is evidence about these 81 files. It is not a measure of accuracy on files in general.
- **Results depend on the engine today.** The strict expected failures and the live-versus-committed test are there so a change to the engine shows up here.
