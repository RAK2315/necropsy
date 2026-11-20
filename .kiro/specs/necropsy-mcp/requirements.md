# Requirements Document

## Introduction

NECROPSY MCP is a Model Context Protocol server that exposes the existing engine to agents, including Kiro. An agent that meets a file it cannot open can ask NECROPSY what the file's structure is, instead of guessing. This is the claim of the whole project, offered where agents work.

The server is a thin wrapper. It calls `Engine`, `emit_spec` and the web service's serialiser, and it re-implements none of them (the boundary in `.kiro/steering/ui.md`). The engine and the web service are not changed. The server is Python on stdio, built on the official MCP Python SDK. A Kiro Power packages the server with a skill on how an agent should treat an unknown file.

Not in scope: a hand-written JSON-RPC layer (the SDK is the reference implementation), a remote or HTTP server (it adds a deploy surface and auth for no evidence gain), and any inference in the wrapper.

## Glossary

- **Server**: the package `necropsy_mcp`, started with `python -m necropsy_mcp`.
- **SDK**: the `mcp` package from PyPI, pinned in design.md.
- **Analysis payload**: the JSON object `web.serialise.to_payload(result, data, engine_ms)` returns, which `/api/analyze` returns to the browser.
- **Input**: exactly one of `path` (a file on the server's machine) or `data_base64` (the bytes, base64-encoded).
- **Structured error**: a JSON object `{"error": <code>, "message": <text>}`, with extra fields where stated.
- **Power**: a directory in the Agent Plugins format that Kiro installs: `plugin.json`, optional `mcp.json`, optional `skills/`.

## Requirements

### Requirement 1: Tools

**User Story:** As an agent, I want to ask NECROPSY about a file's structure, so that I do not guess.

#### Acceptance Criteria

1. THE Server SHALL expose a tool `analyse` taking an Input, and returning the Analysis payload for the file's bytes with exactly three things removed: every candidate's `render.data_b64`, the top-level `spec`, and `value_repr` from every field record (in candidates and in rejected hypotheses). Width, height, channels and note of each `render`, and each field's `name`, `offset`, `fmt` and `value`, stay. Nothing else is removed, added, summarised, dropped or reordered. (Measured in Kiro, the full payload for `mystery_d` was 235,254 characters, and a result over 30,000 characters is shown as only its first and last 500.)
2. THE Server SHALL expose a tool `emit_spec` taking an Input, and returning `{"slug": ..., "files": {name: text}}` for a recovered result, or `{"error": "nothing_recovered", "message": <EmitError.message>}` when the engine's result is FAILED.
3. THE `analyse` payload SHALL be produced by `web.serialise.to_payload` with the same engine and deadline as the web service, then pass through a function that only deletes those two keys. THE Server SHALL NOT build, summarise or reword any part of it.
4. THE `emit_spec` files SHALL come from `necropsy.emit.emit_spec` run on the result of the same engine call.
5. THE tool results SHALL carry the payload as structured content and as one text block holding the same JSON rendered as the web service renders it.
6. THE descriptions of both tools SHALL tell an agent that the result may list several candidates, that all of them close, and that none is to be chosen from the result alone.

### Requirement 2: Limits and input errors

**User Story:** As the operator, I want the same limits as the web service, so that the two surfaces cannot disagree about what a file is allowed to be.

#### Acceptance Criteria

1. THE Server SHALL refuse an input larger than 65,536 bytes with the structured error `file_too_large` carrying `limit_bytes: 65536`, before the engine runs.
2. THE Server SHALL run the engine with `deadline_seconds=5.0`, as the web service does. A test SHALL assert both constants equal the web service's.
3. WHEN neither or both of `path` and `data_base64` are given, THE Server SHALL return the structured error `bad_input`.
4. WHEN `data_base64` is not valid base64, THE Server SHALL return `invalid_base64`.
5. WHEN `path` names no file, a directory, or an unreadable file, THE Server SHALL return `file_not_found`, `not_a_file` or `unreadable`.
6. WHEN reading a path, THE Server SHALL read at most 65,537 bytes, so an oversize or endless file is never read in full.
7. EVERY input error SHALL be returned as a tool result with `isError` true. A FAILED engine result and `nothing_recovered` SHALL NOT be errors: they are normal outcomes.
8. THE tools SHALL NOT raise on any input. Arbitrary bytes up to 65,536 SHALL produce a valid payload or a structured error.

### Requirement 3: Registration

**User Story:** As a Kiro user, I want the server registered in the workspace, so that Kiro can call it.

#### Acceptance Criteria

1. THE file `.kiro/settings/mcp.json` SHALL register the server over stdio with the command `python` and arguments `-m necropsy_mcp`.
2. THE registration SHALL NOT auto-approve any tool.

### Requirement 4: Proof against the engine

**User Story:** As the builder, I want evidence that the wrapper changes nothing, so that I can rely on it.

#### Acceptance Criteria

1. A test SHALL start the server as a subprocess over stdio, connect with the SDK's client, and call both tools on all 11 samples and on all 81 real-corpus files.
2. FOR EACH file within the limit, THE result's status, candidate count and fields SHALL equal `Engine().run` on the same bytes, and the payload SHALL be byte-identical to `to_payload` output with those three removals applied, once `engine_ms` is set to the same value.
3. FOR EACH real-corpus file over the limit, THE result SHALL be the structured error the web service's 413 body states.
4. THE `emit_spec` files SHALL equal `emit_spec(Engine().run(data), data)`.
5. A Hypothesis property test SHALL show `analyse` never raises on `st.binary(max_size=65536)` and returns a valid payload or a structured error.
6. THE break checks SHALL show the tests catch: the wrapper truncating the input, the wrapper reordering candidates, `emit_spec` returning a stale spec, the wrapper also dropping a candidate's fields, the wrapper keeping the pixel buffers, the wrapper dropping each field's `value` instead of `value_repr`, and the wrapper keeping `value_repr`.
7. A test SHALL show that, for every field of every candidate and rejected hypothesis on all 92 files, `value_repr` is rebuilt exactly from `value`, before `value_repr` is removed.
8. THE `analyse` result for every corpus file within the limit SHALL be under 30,000 characters, which is Kiro's limit (a longer result is shown as only its first and last 500, and the full output is saved to a file). It is Kiro's limit, not a number chosen here.
9. IF any file's MCP result differs from the engine's, THEN the builder SHALL stop and report. IF the SDK requires Python above 3.10, THEN the builder SHALL stop and report.

### Requirement 5: Use from Kiro chat

**User Story:** As a judge, I want to see Kiro itself use the tool, so that the claim is shown where agents work.

#### Acceptance Criteria

1. IN Kiro chat, Kiro SHALL be asked to call `analyse` on `spike/samples/mystery_d`. IT SHALL report 18 candidates and choose none.
2. THE exact call and response SHALL be recorded in `docs/KIRO-LOG.md`.

### Requirement 6: The Power

**User Story:** As a Kiro user, I want one installable package, so that I get the server and the guidance together.

#### Acceptance Criteria

1. THE Power SHALL follow the layout in Kiro's current documentation: `plugin.json` (required), `mcp.json`, and `skills/<name>/SKILL.md`. The format SHALL be read from the documentation before any Power file is written, and recorded in design.md.
2. THE Power SHALL bundle the server and what it imports, generated from the repository by `tools/build_power.py`, so that it runs from its own directory with only the SDK installed. A test SHALL fail if the bundle differs from the source.
3. THE Power's `mcp.json` SHALL start the server with the working directory `${PLUGIN_ROOT}`.
4. THE Power's skill SHALL tell an agent: call `analyse` first on an unknown file; report every candidate; never pick one unless the result is RESOLVED; say what a FAILED result states and stop; when a tool result arrives truncated, read the saved full output before answering and never report candidates from a truncated view.
5. THE Power's `plugin.json` and `mcp.json` SHALL validate against the Agent Plugins JSON schemas, and its skill SHALL satisfy the Agent Skills frontmatter rules.
6. A test SHALL start the server from the Power's own `mcp.json` (its command, arguments and working directory) and call `analyse` successfully.
7. THE Power's tool SHALL be callable from Kiro after installing the Power. THIS cannot be tested from outside Kiro, and the design SHALL say so.
