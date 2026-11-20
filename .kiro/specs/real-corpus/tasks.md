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

- [ ] 4. Open, not part of this spec
  - The five in-scope failures are diagnosed in another session. When one is fixed, its strict expected failure errors: regenerate with `python -m tools.real_corpus`, remove the marker, and update the counts in design.md.
