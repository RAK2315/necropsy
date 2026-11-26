"""Held-out set: keep it unseen during development, then prove it was fixed in advance.

Until they were evaluated (once, 26 Nov 2026), the held-out files and their
manifest lived OUTSIDE this repository, in ``%LOCALAPPDATA%/necropsy-heldout/``,
and the repository held only the commitment
(``spike/samples/heldout/COMMITMENT.md``): the SHA-256 of the sealed manifest
and of every file. They are now published in ``spike/samples/heldout/`` with
``RESULTS.md``; ``verify`` checks the published copy against the commitment.
The guard stays on, so the agent never tunes the engine against them.

Subcommands:

``guard``
    Kiro PreToolUse hook (``.kiro/hooks/heldout-guard.json``). Reads the hook
    payload as JSON on stdin and exits 2, which blocks the tool call, when the
    tool input names the held-out folder or any held-out file. Exits 0
    otherwise, and on any internal error, so a fault here never stops Kiro.

``verify``
    Recomputes the sealed manifest's SHA-256 and every file's SHA-256 and
    compares them with ``COMMITMENT.md``. Exit 0 only if all match.

Written by Claude Code (not Kiro).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMITMENT = ROOT / "spike" / "samples" / "heldout" / "COMMITMENT.md"
FOLDER_TOKEN = "necropsy-heldout"


REPO_COPY = ROOT / "spike" / "samples" / "heldout"
REPO_TOKEN = "samples/heldout"


def heldout_dir() -> Path:
    env = os.environ.get("NECROPSY_HELDOUT_DIR")
    if env:
        return Path(env)
    if (REPO_COPY / "manifest.json").is_file():
        return REPO_COPY
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / FOLDER_TOKEN


def heldout_names() -> list[str]:
    try:
        manifest = json.loads((heldout_dir() / "manifest.json").read_text(encoding="utf-8"))
        return [f["file"] for f in manifest["files"]]
    except Exception:
        return []


def guard() -> int:
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw or "{}")
            text = json.dumps(payload.get("tool_input", payload), ensure_ascii=False)
        except Exception:
            text = raw  # unparseable payload: scan it as text rather than let it through
        # JSON escapes backslashes; fold them so Windows paths match too.
        hay = text.replace("\\\\", "/").replace("\\", "/").lower()
        hits = [t for t in (FOLDER_TOKEN, REPO_TOKEN) if t in hay]
        hits += [n for n in heldout_names() if n.lower() in hay]
        if hits:
            sys.stderr.write(
                "Blocked by the held-out guard: this tool call names the held-out set "
                f"({', '.join(sorted(set(hits))[:5])}). That set was evaluated once by "
                "Claude Code and its results are published; using it to develop or tune the "
                "engine would void them. Do not read, copy, list, mention or test against it.\n"
            )
            return 2
    except Exception:
        return 0
    return 0


def committed_hashes() -> tuple[str | None, set[str]]:
    text = COMMITMENT.read_text(encoding="utf-8")
    m = re.search(r"Manifest SHA-256: `([0-9a-f]{64})`", text)
    files = set(re.findall(r"^- `([0-9a-f]{64})`$", text, flags=re.M))
    return (m.group(1) if m else None), files


def verify() -> int:
    d = heldout_dir()
    want_manifest, want_files = committed_hashes()
    raw = (d / "manifest.json").read_bytes()
    got_manifest = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(raw.decode("utf-8"))
    got_files = set()
    bad = []
    for f in manifest["files"]:
        h = hashlib.sha256((d / "files" / f["file"]).read_bytes()).hexdigest()
        got_files.add(h)
        if h != f["sha256"]:
            bad.append(f["file"])
    ok = got_manifest == want_manifest and got_files == want_files and not bad
    print(f"manifest sha256 {got_manifest} {'matches' if got_manifest == want_manifest else 'DOES NOT MATCH'} the commitment")
    print(f"files: {len(got_files)} hashed, {len(want_files)} committed, "
          f"{len(got_files ^ want_files)} differ, {len(bad)} disagree with the manifest")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["guard"]:
        return guard()
    if argv[:1] == ["verify"]:
        return verify()
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
