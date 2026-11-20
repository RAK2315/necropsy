"""Input handling and the two tool bodies. No MCP types, no inference.

`analyse` and `emit` call Engine, web.serialise.to_payload and necropsy.emit.emit_spec and
build nothing themselves. Every function returns a value; none raises.
"""
from __future__ import annotations

import base64
import binascii
import time

from necropsy.emit import EmittedSpec, emit_spec as _emit_spec
from necropsy.engine import Engine
from web.serialise import to_payload

MAX_BYTES = 65_536            # same as app.MAX_UPLOAD (asserted by a test)
DEADLINE_SECONDS = 5.0        # same as app.py's Engine(deadline_seconds=5.0)
_MAX_B64_CHARS = ((MAX_BYTES + 2) // 3) * 4   # longest padded base64 text of MAX_BYTES bytes


def error(code: str, message: str, **extra) -> dict:
    return {"error": code, "message": message, **extra}


def _too_large() -> dict:
    return error("file_too_large", f"The file is larger than the {MAX_BYTES:,} byte limit.",
                 limit_bytes=MAX_BYTES)


def load(path, data_base64) -> bytes | dict:
    """The input bytes, or a structured error dict. Reads at most MAX_BYTES + 1 bytes of a file."""
    try:
        if (path is None) == (data_base64 is None):
            return error("bad_input", "Give exactly one of `path` and `data_base64`.")
        if data_base64 is not None:
            if not isinstance(data_base64, str):
                return error("bad_input", "`data_base64` must be a string.")
            text = data_base64.strip()
            if len(text) > _MAX_B64_CHARS:
                return _too_large()
            try:
                data = base64.b64decode(text, validate=True)
            except (binascii.Error, ValueError):
                return error("invalid_base64", "`data_base64` is not valid base64.")
        else:
            if not isinstance(path, str) or not path or "\x00" in path:
                return error("bad_input", "`path` must be a non-empty string without NUL bytes.")
            try:
                with open(path, "rb") as f:
                    data = f.read(MAX_BYTES + 1)
            except FileNotFoundError:
                return error("file_not_found", f"No file at {path!r}.")
            except (IsADirectoryError, NotADirectoryError):
                return error("not_a_file", f"{path!r} is not a file.")
            except PermissionError:
                return error("unreadable", f"{path!r} cannot be read.")
            except OSError as exc:
                # Windows reports a directory as PermissionError, and other faults as OSError.
                return error("unreadable", f"{path!r} cannot be read ({type(exc).__name__}).")
        if len(data) > MAX_BYTES:
            return _too_large()
        return data
    except Exception as exc:  # last line of defence; the tools never raise
        return error("internal_error", f"{type(exc).__name__}")


def analyse(path=None, data_base64=None) -> tuple[dict, bool]:
    """(payload or structured error, is_error)."""
    data = load(path, data_base64)
    if isinstance(data, dict):
        return data, True
    try:
        start = time.perf_counter()
        result = Engine(deadline_seconds=DEADLINE_SECONDS).run(data)
        engine_ms = (time.perf_counter() - start) * 1000.0
        return to_payload(result, data, engine_ms), False
    except Exception as exc:
        return error("internal_error", f"{type(exc).__name__}"), True


def emit(path=None, data_base64=None) -> tuple[dict, bool]:
    """({"slug", "files"} or nothing_recovered or a structured error, is_error)."""
    data = load(path, data_base64)
    if isinstance(data, dict):
        return data, True
    try:
        result = Engine(deadline_seconds=DEADLINE_SECONDS).run(data)
        spec = _emit_spec(result, data)
        if isinstance(spec, EmittedSpec):
            return {"slug": spec.slug, "files": {n: t for n, t in spec.files}}, False
        return error("nothing_recovered", getattr(spec, "message", "")), False
    except Exception as exc:
        return error("internal_error", f"{type(exc).__name__}"), True
