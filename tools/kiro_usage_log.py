"""Append one row to docs/KIRO-LOG.md for each file the Kiro agent writes.

Invoked by .kiro/hooks/kiro-usage-log.json on PostFileSave / PostFileCreate.
Kiro passes session context as JSON on stdin, including `file_path`.
This script must never fail the agent: every error is swallowed, and it
prints nothing (stdout from a hook is fed back into the agent's context).
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "KIRO-LOG.md"


def head_short() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "no-commit"
    except Exception:
        return "unknown"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    if not isinstance(payload, dict) or not payload.get("file_path"):
        return
    raw = str(payload["file_path"])
    try:
        rel = Path(raw).resolve().relative_to(ROOT).as_posix()
    except Exception:
        rel = raw.replace("\\", "/")

    if rel == "docs/KIRO-LOG.md":
        return

    event = payload.get("hook_event_name", "?")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    row = f"| {stamp} | {event} | `{rel}` | `{head_short()}` |\n"

    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(row)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
