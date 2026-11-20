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

- [ ] 5. Kiro chat check
  - In a fresh Kiro session, with `.kiro/settings/mcp.json` loaded, ask Kiro to call `analyse` on `spike/samples/mystery_d`. Expect 18 candidates and no choice.
  - Record the exact call and response in `docs/KIRO-LOG.md`.
  - Not done: the session that built this spec already listed a `necropsy` server before these files existed, so a call from it cannot be attributed to this server.
  - _Requirements: 5.1, 5.2_

- [ ] 6. Install the Power in Kiro
  - Powers panel, Add Custom Power, Import power from a folder, `powers/necropsy`. Confirm the tools appear and the skill activates.
  - _Requirements: 6.7_
