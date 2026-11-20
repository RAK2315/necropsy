# Implementation Plan: Real Corpus

## Tasks

- [x] 1. Differential runner (`tools/real_corpus.py`)
  - Engine over all 81 files, canonical pixel comparison with Pillow, raw results committed first.
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

- [x] 2. Decisions applied, results table, test
  - Scope override, notes, expectations; `docs/REAL-CORPUS-RESULTS.md` generated; `tests/test_real_corpus.py`.
  - Five in-scope failures as strict expected failures; rgba16 as a known interpretation difference.
  - _Requirements: 1.3, 1.4, 2.4 to 2.6, 3, 4, 5, 6_

- [x] 3. Spec
  - Requirements, design with results as measured, decisions and limits.

- [x] 4. The five in-scope failures (fixed by the engine, outside this spec)
  - All five were fixed. The committed results history shows when each first RESOLVED, with pixels matching Pillow's:
    - `goimage_no_compress.tiff`, `goimage_no_rps.tiff`, `goimage_video-001-uncompressed.tiff` and `sdlimage_sample.tif`: commit `402d0e3` (Task 16.3, the TIFF probe reads the BitsPerSample array; engine Decision Record item 20).
    - `pillow_p_16.tga`: commit `1f26f4d` (Task 18, a TGA 2.0 footer's declared offsets end the data region; engine Decision Record item 22).
  - The regenerated table has 2 in-scope FAILED files, `pillow_01r_00.pcx` and `pillow_p_8.tga`, both invalid by construction, where Pillow also refuses. Design.md's counts were checked against `docs/REAL-CORPUS-RESULTS.md` and match: 23 match, 1 known interpretation difference, 2 invalid FAILED, 54 out-of-scope FAILED, 1 invalid RESOLVED (ossfuzz); 25 RESOLVED and 56 FAILED in total.
  - `OPEN_IN_SCOPE_FAILURES` is empty and a test states it. The strict expected-failure mechanism stays for any future entry.
