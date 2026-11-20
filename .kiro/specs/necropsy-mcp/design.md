# Design Document

## Overview

```
agent (Kiro) --stdio--> necropsy_mcp.server --> necropsy_mcp.core --> Engine, web.serialise.to_payload, necropsy.emit.emit_spec
```

- `necropsy_mcp/core.py`: input handling and the two tool bodies. No MCP types, no inference.
- `necropsy_mcp/server.py`: registers `analyse` and `emit_spec` on the SDK's `MCPServer` and runs stdio.
- `necropsy_mcp/__main__.py`: `python -m necropsy_mcp`.
- `powers/necropsy/`: the Power. `tools/build_power.py` generates its bundle.

The engine and the web service are not changed. `core.py` duplicates four lines of `app._analyse` (the engine call with `deadline_seconds=5.0`, the timer, `to_payload`) rather than import `app.py`, which would pull FastAPI into the server. A test asserts the constants equal the web service's.

## SDK

`mcp==2.3.0`, the official Model Context Protocol Python SDK. PyPI lists `requires_python >=3.10` for this release, and the project runs Python 3.10.11, so nothing above 3.10 is required. The server uses `mcp.server.mcpserver.MCPServer`. The tests use `mcp.Client` with `StdioServerParameters`. No JSON-RPC is written by hand. CI installs the same pin.

## Tools

| | `analyse` | `emit_spec` |
|---|---|---|
| Arguments | `path` or `data_base64`, exactly one | same |
| Result | `web.serialise.to_payload(result, data, engine_ms)` minus every candidate's `render.data_b64` and the top-level `spec` | `{"slug", "files": {name: text}}` from `emit_spec`, or `{"error": "nothing_recovered", "message"}` |
| `isError` | false for every engine outcome, including FAILED | same; `nothing_recovered` is a normal outcome |

Both tools return a `CallToolResult` with structured content (the object) and one text block holding the same JSON rendered as Starlette's `JSONResponse` renders it (`ensure_ascii=False`, compact separators). A test checks the text equals `JSONResponse(payload).body`.

Input errors are `isError` true with `{"error", "message"}`: `bad_input`, `invalid_base64`, `file_not_found`, `not_a_file`, `unreadable`, `file_too_large` (with `limit_bytes: 65536`, the web service's 413 body), `internal_error`.

A path is read with `open(path, "rb").read(65537)`, so a large or endless file is never read in full. A base64 string longer than the longest padded encoding of 65,536 bytes is refused before it is decoded.

## Proof

Run: `python -m pytest tests/test_mcp_server.py tests/test_power.py -q`.

The server is started as a subprocess over stdio, and every call goes through the SDK's client. The sweep covers the 11 samples and the 81 real-corpus files (92 files). 82 are within the 65,536-byte limit and 10 real-corpus files are over it.

| Check | Result |
|---|---|
| `analyse` on 82 files within the limit: status, candidate count, fields, payload | equal to `Engine().run` and to `to_payload` minus the two keys on the same bytes; payload byte-identical to `to_payload` minus those two keys, once `engine_ms` is set to the same value |
| `emit_spec` on 82 files: slug and files, or the `EmitError` message | equal to `emit_spec(Engine().run(data), data)` |
| 10 real files over the limit, both tools | the web service's 413 body, `isError` true |
| mystery_d | UNRESOLVED_AMBIGUITY, 18 candidates, no field naming a choice |
| property: `analyse` on `st.binary(max_size=65536)` | never raises; a valid payload |
| property: arbitrary `path` and `data_base64` arguments (text, bytes, None) to both tools | never raise; structured errors |

No file's MCP result differed from the engine's. The 10 oversize files are refused by the limit that Requirement 2.1 states, which is the web service's limit. The server returns no engine result for them, so there is nothing to compare, and the refusal itself equals the web service's.

### Break checks

`python tools/break_check.py tests/break_checks/mcp.json`. Each break is applied to `necropsy_mcp/core.py`, the guarding test is run, the file is restored and its hash checked.

| Break | Result |
|---|---|
| wrapper truncates the input by one byte before the engine | caught (status and payload differ on `mystery_a` and others) |
| wrapper reverses the candidate list | caught (payload and fields differ on `mystery_d`) |
| wrapper also drops a candidate's fields | caught (fields missing, payload differs) |
| wrapper keeps the pixel buffers | caught (payload differs) |
| `emit_spec` returns the first spec it produced for every later call | caught (spec differs on every file after the first) |

## Size

`analyse` first returned the whole web payload. In a fresh Kiro session that was 235,254 characters for `mystery_d` and the client truncated it. The cause is each candidate's pixel buffer (`render.data_b64`) and the emitted spec inside the payload. The change removes exactly those two things and nothing else (`core.agent_sized`), so every status, candidate, field, rejection and reason is the engine's and in the engine's order. A wrapper-written summary was rejected: it would be text the engine did not produce.

Measured after the change, `mystery_d`: **32,236 characters** (the figure moves by a character or two with `engine_ms`). Eighteen candidates account for 31,909 of them, about 1,800 each, of which each candidate's `fields` list is about 2,500 on the first candidate. That is 7 times smaller than 235,254 but not under the 20,000 target in Requirement 1.7. `test_analyse_on_mystery_d_is_under_20000_characters` states the target and is a strict expected failure, so it stays visible and turns into an error when the size reaches it. Meeting it needs a third removal (for example each field's `value_repr`, which repeats `value`) or fewer fields per candidate. That is a decision, not made here. The result also travels twice (structured content and one text block), which the client may count.

## Registration

`.kiro/settings/mcp.json`:

```json
{ "mcpServers": { "necropsy": { "command": "python", "args": ["-m", "necropsy_mcp"], "disabled": false } } }
```

No `autoApprove`. Kiro's documented keys for a workspace server do not include a working directory, so this relies on Kiro starting the command in the workspace root, where `necropsy_mcp` is importable. A test starts the server from the repository root with these arguments. That Kiro does start it from there is shown only by the check in Kiro chat (Requirement 5).

## The Power

Read from Kiro's documentation (kiro.dev/docs/powers, kiro.dev/docs/powers/create) and the Agent Plugins 1.0.0 specification (agent-plugins.org/specification) before any Power file was written.

```
powers/necropsy/
├── plugin.json            required: $schema, name, version, description, author.name, keywords
├── mcp.json               stdio server; command "python"; args ["-m", "necropsy_mcp"]; cwd "${PLUGIN_ROOT}"
├── requirements.txt       mcp==2.3.0
├── README.md
├── skills/unknown-file/SKILL.md   frontmatter: name, description
└── necropsy/  necropsy_mcp/  web/ generated by tools/build_power.py
```

- **The guidance is a skill, not a steering file.** The current Power format has `skills/` and no steering. The skill tells an agent to call `analyse` first, report every candidate, never pick one, and on FAILED to report the termination and stop.
- **The Power is self-contained.** Its server and everything it imports (`necropsy/`, `necropsy_mcp/`, and `web/__init__.py`, `serialise.py`, `pixels.py`) are copied in by `tools/build_power.py`, so it runs with `cwd` set to `${PLUGIN_ROOT}` and only the SDK installed. `tests/test_power.py` fails when the bundle differs from the source, and shows the check catching a changed file.
- **Validation.** `plugin.json` and `mcp.json` are validated against copies of the two published schemas in `tests/support/agent_plugins/` (fetched from agent-plugins.org, kept so the tests run offline). The skill's frontmatter is checked against the Agent Skills rules (name pattern and length, name equals directory, description length).
- **Install and call.** The test copies the Power to another folder, as an install does, starts the server from that copy's `mcp.json` (command, arguments and working directory, with `PYTHONPATH` removed), checks that `necropsy`, `necropsy_mcp` and `web.serialise` import from the copy, and calls `analyse` on `mystery_d`: 18 candidates.

## Limits

- **Not shown from outside Kiro:** that Kiro's installer accepts the folder, that Kiro activates the skill on its keywords, and that Kiro calls the tool. The Kiro chat check in Requirement 5 covers the call and is recorded when done.
- **Payload size.** `analyse` omits the pixel buffers and the spec and is still about 32,000 characters for `mystery_d` (see "Size").
- **A file's path is read from the server's machine.** The server is local, over stdio, with no network. It reads the file the agent names and nothing else.
- **`python` must be on the PATH Kiro uses**, with `mcp==2.3.0` installed.
