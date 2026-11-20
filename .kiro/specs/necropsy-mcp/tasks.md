# Implementation Plan: NECROPSY MCP

## Tasks

- [x] 1. Server (`necropsy_mcp/`)
  - `analyse` and `emit_spec` over stdio on `mcp==2.3.0`; limits and errors as in design.md.
  - _Requirements: 1, 2_

- [x] 2. Registration and CI
  - `.kiro/settings/mcp.json`; `mcp==2.3.0` added to the CI install line.
  - _Requirements: 3_

- [x] 3. Proof (`tests/test_mcp_server.py`)
  - Stdio sweep over 92 files against `Engine`, `to_payload` and `emit_spec`; Hypothesis properties.
  - Break checks (`tests/break_checks/mcp.json`): truncation, reordering, stale spec. All three caught.
  - _Requirements: 4_

- [x] 4. Power (`powers/necropsy/`, `tools/build_power.py`, `tests/test_power.py`)
  - Layout read from Kiro's documentation first. Bundle generated and checked; schemas and skill rules validated; server started from the Power's own `mcp.json` in an installed copy.
  - _Requirements: 6.1 to 6.6_

- [x] 5. Kiro chat check
  - Both checks recorded as measured in `docs/KIRO-LOG.md` (section "NECROPSY MCP: checks in a fresh Kiro session"): `analyse` on `mystery_d` (UNRESOLVED_AMBIGUITY, 18 candidates, none chosen, 235,254 characters, truncated by the client) and `emit_spec` on `mystery_e` (slug `tiff`).
  - _Requirements: 5.1, 5.2_

- [x] 5a. Agent-sized `analyse`
  - Removed `render.data_b64` and `spec` (235,254 to 32,236 characters for `mystery_d`).
  - _Requirements: 1.1, 1.3, 4.2_

- [x] 5b. Under Kiro's 30,000-character limit
  - `value_repr` removed from every field after a test rebuilt it from `value` on all 92 files; the 20,000 target replaced by Kiro's measured limit; skill reads the saved full output when a result is truncated; two more break checks. `mystery_d`: 25,890.
  - _Requirements: 1.1, 4.7, 4.8, 6.4_

- [x] 6. Install the Power in Kiro
  - Installed from `powers/necropsy` into an empty workspace; Kiro activated it, read the skill and called `analyse` on `mystery_b`. Recorded in `docs/KIRO-LOG.md`.
  - _Requirements: 6.7_

