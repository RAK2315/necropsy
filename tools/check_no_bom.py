"""Fail if any file under .kiro/ starts with a UTF-8 byte-order mark.

A BOM before the `---` line breaks Kiro's steering front matter, and
Windows PowerShell 5.1 adds one silently when it writes UTF-8.

Usage:
    python tools/check_no_bom.py          # check; exit 1 if any BOM found
    python tools/check_no_bom.py --fix    # strip BOMs in place

Run automatically by .githooks/pre-commit.
"""

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".kiro"


def files_with_bom():
    for path in sorted(TARGET.rglob("*")):
        if path.is_file():
            with path.open("rb") as f:
                if f.read(3) == BOM:
                    yield path


def main(argv) -> int:
    fix = "--fix" in argv
    found = list(files_with_bom())
    for path in found:
        rel = path.relative_to(ROOT).as_posix()
        if fix:
            path.write_bytes(path.read_bytes()[len(BOM):])
            print(f"stripped BOM: {rel}")
        else:
            print(f"BOM found: {rel}")
    if found and not fix:
        print("Fix with: python tools/check_no_bom.py --fix")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
