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
  - Removed `render.data_b64` and `spec`; sweep equals `to_payload` minus those keys; two more break checks caught. Size 32,236 for `mystery_d`: the under-20,000 test is a strict expected failure pending a decision.
  - _Requirements: 1.1, 1.3, 4.2, 4.6, 4.7_

- [ ] 6. Install the Power in Kiro
  - Powers panel, Add Custom Power, Import power from a folder, `powers/necropsy`. Confirm the tools appear and the skill activates.
  - _Requirements: 6.7_
