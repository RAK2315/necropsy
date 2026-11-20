"""Break a claim on purpose, run the test that guards it, restore the file, and prove the restore.

python tools/break_check.py <breaks.json>

breaks.json: a list of {"name", "file", "old", "new", "test"}. `old` must occur exactly once in `file`.
`test` is a pytest node id or "path -k expr". For each break: the file's SHA-256 before, the test result with
the break applied, and the SHA-256 after restoring. A break whose test still passes is reported as NOT CAUGHT.
The file is restored in a finally block, even if pytest crashes.
"""
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main(spec_path: str) -> int:
    breaks = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    missed = 0
    for b in breaks:
        p = ROOT / b["file"]
        original = p.read_bytes()
        before = sha(p)
        text = original.decode("utf-8")
        count = text.count(b["old"])
        if count != 1:
            print(f"BREAK  {b['name']}: anchor occurs {count} times in {b['file']}, skipped")
            missed += 1
            continue
        p.write_bytes(text.replace(b["old"], b["new"]).encode("utf-8"))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", *shlex.split(b["test"]), "-q", "--tb=line", "-p", "no:warnings"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        finally:
            p.write_bytes(original)
        after = sha(p)
        lines = r.stdout.splitlines()
        summary = next((l.strip() for l in reversed(lines) if " passed" in l or " failed" in l or " error" in l), "?")
        why = next((l.strip() for l in lines if "Error" in l or "assert" in l.lower()), "")
        caught = r.returncode != 0
        missed += not caught
        print(f"BREAK  {b['name']}  ({b['file']})")
        print(f"  with break : {summary}  -> {'caught' if caught else 'NOT CAUGHT'}")
        if why:
            print(f"  failure    : {why[:300]}")
        print(f"  restored   : sha256 {before} -> {after} {'identical' if before == after else 'DIFFERENT'}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
