# Implementation Plan: Gate Adversary

## Tasks

- [x] 1. Blind generator and measurement (`tools/adversary.py`)
  - Generator of the five axes in design.md "Axes", a function of the file size only.
  - `run_adversary` with the exclusion rule and the separate respelled count.
  - `python -m tools.adversary` writes `tools/adversary_counts.json` for all 11 samples.
  - Tests in `tests/test_adversary_tool.py`.
  - _Requirements: 1.1 to 1.8_

- [x] 2. Spec and finding
  - `requirements.md`, `design.md` with the Finding and the measured counts.
  - One cross-reference line (item 19) in the engine spec's Decision Record. No requirement changes.
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Perturbation test (`tests/test_gate_perturbation.py`)
  - Table of offsets and original values per sample; table checked against the files.
  - Tracks-or-fails assertion, never the unperturbed answer.
  - Non-vacuity per sample, recogniser teeth test, Hypothesis property test.
  - Stop and report if any perturbation returns the unperturbed answer. None did.
  - _Requirements: 2.1 to 2.10_
