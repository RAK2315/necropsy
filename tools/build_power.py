"""Copy the server and what it imports into the Power, so the Power runs from its own directory.

python tools/build_power.py          # write the bundle
python tools/build_power.py --check  # exit 1 if the bundle differs from the source

The bundle is generated. The Power's own files (plugin.json, mcp.json, skills/, README.md,
requirements.txt) are written by hand and are not touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POWER = ROOT / "powers" / "necropsy"
# (source relative to the repo, destination relative to the Power): whole packages, and three files of web/.
PACKAGES = ("necropsy", "necropsy_mcp")
WEB_FILES = ("__init__.py", "serialise.py", "pixels.py")


def expected() -> dict[str, bytes]:
    """Relative path in the Power -> bytes."""
    out: dict[str, bytes] = {}
    for pkg in PACKAGES:
        for p in sorted((ROOT / pkg).rglob("*.py")):
            if "__pycache__" not in p.parts:
                out[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    for name in WEB_FILES:
        out[f"web/{name}"] = (ROOT / "web" / name).read_bytes()
    return out


def present() -> set[str]:
    found: set[str] = set()
    for top in (*PACKAGES, "web"):
        d = POWER / top
        if d.exists():
            found |= {p.relative_to(POWER).as_posix() for p in d.rglob("*") if p.is_file()
                      and "__pycache__" not in p.parts}
    return found


def differences() -> list[str]:
    want = expected()
    problems = []
    for rel, data in want.items():
        target = POWER / rel
        if not target.exists():
            problems.append(f"missing {rel}")
        elif target.read_bytes() != data:
            problems.append(f"differs {rel}")
    problems += [f"extra {rel}" for rel in sorted(present() - set(want))]
    return problems


def build() -> None:
    want = expected()
    for rel in sorted(present() - set(want)):
        (POWER / rel).unlink()
    for rel, data in want.items():
        target = POWER / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


if __name__ == "__main__":
    if "--check" in sys.argv:
        problems = differences()
        print("\n".join(problems) or "bundle matches the source")
        sys.exit(1 if problems else 0)
    build()
    print(f"bundled {len(expected())} files into {POWER.relative_to(ROOT)}")
