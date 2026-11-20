"""The MCP server: two tools over stdio, built on the official SDK (pinned in design.md)."""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from necropsy_mcp import core

INSTRUCTIONS = (
    "Use these tools when you hold a file whose layout you do not know. `analyse` infers the structure "
    "from the bytes and checks it by arithmetic. When more than one layout closes, the bytes cannot "
    "separate them: report all of them and choose none."
)
_INPUT = (
    "Give exactly one of `path` (a file on this machine) or `data_base64` (the bytes, base64). "
    f"At most {core.MAX_BYTES:,} bytes."
)

server = MCPServer("necropsy", instructions=INSTRUCTIONS, version="1.0.0")


def render(obj: dict) -> str:
    """JSON text exactly as the web service renders a response body (Starlette's JSONResponse)."""
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"))


def to_result(obj: dict, is_error: bool) -> CallToolResult:
    return CallToolResult(content=[TextContent(text=render(obj))], structured_content=obj, is_error=is_error)


@server.tool(
    name="analyse",
    description=(
        "Infer the structure of a file from its bytes. Returns the analysis payload the NECROPSY web "
        "service returns: status RESOLVED (one layout closes), UNRESOLVED_AMBIGUITY (several layouts close; "
        "the bytes cannot separate them, so report every candidate and choose none) or FAILED (nothing "
        "closed; the payload says what was tried and why the search stopped). " + _INPUT
    ),
)
def analyse(path: str | None = None, data_base64: str | None = None) -> CallToolResult:
    payload, is_error = core.analyse(path, data_base64)
    return to_result(payload, is_error)


@server.tool(
    name="emit_spec",
    description=(
        "Emit the spec files (requirements.md, design.md and an acceptance test) that describe a recovered "
        "file's layout. Returns {slug, files}, or {error: nothing_recovered, message} when the result is "
        "FAILED. When several candidates close, the spec lists every candidate and chooses none. " + _INPUT
    ),
)
def emit_spec(path: str | None = None, data_base64: str | None = None) -> CallToolResult:
    payload, is_error = core.emit(path, data_base64)
    return to_result(payload, is_error)


def main() -> None:
    server.run(transport="stdio")
