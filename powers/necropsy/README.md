# NECROPSY Power

Gives Kiro two tools, `analyse` and `emit_spec`, and a skill, `unknown-file`, on how to treat a file it cannot open.

## Layout

```
plugin.json                 manifest (Agent Plugins 1.0.0)
mcp.json                    starts the server: python -m necropsy_mcp, cwd ${PLUGIN_ROOT}
skills/unknown-file/SKILL.md
requirements.txt            mcp==2.3.0
necropsy/ necropsy_mcp/ web/   the server and what it imports (generated)
```

The last three folders are generated from the repository by `python tools/build_power.py`. Do not edit them. A test fails when they differ from the source.

## Install

1. `python -m pip install -r requirements.txt` (Python 3.10 or later; `python` must be on the PATH Kiro uses).
2. In Kiro: Powers panel, Add Custom Power, Import power from a folder, select this folder.
3. Ask Kiro about a file it cannot open. The skill activates on keywords such as "unknown file" and "mystery file".
