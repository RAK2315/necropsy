"""Spec emission: build the three spec files and write them to disk.

emit_spec is pure. write_spec is the only function that writes files, only inside
the given directory and only for a valid slug. Neither function raises.

Newline choice: file text is encoded to UTF-8 and written as bytes, so "\\n" in the
rendered text stays "\\n" on every platform (no CRLF translation) and no BOM is added.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

from necropsy.emit.layout import build_layout
from necropsy.emit.render import render_design, render_requirements, render_tests

_SLUG_RE = re.compile(r"[a-z0-9-]+")
_FILE_NAMES = ("requirements.md", "design.md", "tests.py")


@dataclass(frozen=True)
class EmittedSpec:
    slug: str
    files: tuple  # ((name, text), ...) for requirements.md, design.md, tests.py


@dataclass(frozen=True)
class EmitError:
    message: str


def emit_spec(result, data):
    """Build an EmittedSpec from an engine result, or an EmitError. Never raises."""
    try:
        data = bytes(data)
        layout = build_layout(result, data)
        if not isinstance(layout, dict) or layout.get("kind") == "error":
            msg = layout.get("error") if isinstance(layout, dict) else None
            return EmitError(str(msg or "layout error"))
        slug = layout.get("slug")
        if not isinstance(slug, str):
            return EmitError("layout error: missing slug")
        texts = (
            render_requirements(layout, result, data),
            render_design(layout, result, data),
            render_tests(layout, result, data),
        )
        return EmittedSpec(slug, tuple(zip(_FILE_NAMES, texts)))
    except Exception as exc:
        return EmitError("emit error: " + type(exc).__name__)


def write_spec(spec, out_dir, overwrite=False):
    """Write spec into out_dir/<slug>/. Returns the folder path or an EmitError. Never raises."""
    try:
        slug = getattr(spec, "slug", None)
        if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
            return EmitError("invalid slug")
        files = tuple(getattr(spec, "files", ()))
        if tuple(n for n, _ in files) != _FILE_NAMES:
            return EmitError("invalid files")
        base = pathlib.Path(out_dir).resolve()
        target = (base / slug).resolve()
        if target.parent != base:
            return EmitError("path escapes output directory")
        if target.exists() and not overwrite:
            return EmitError("already exists: " + slug)
        if target.exists() and not target.is_dir():
            return EmitError("not a directory: " + slug)
        target.mkdir(parents=True, exist_ok=True)
        for name, text in files:
            (target / name).write_bytes(str(text).encode("utf-8"))
        return target
    except Exception as exc:
        return EmitError("write error: " + type(exc).__name__)
