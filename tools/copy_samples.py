"""Copy the sample files into public/samples/ and write samples/index.json.

The index holds only name, size and, for external samples, a provenance line. Never an outcome.
Run from anywhere: python tools/copy_samples.py
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "spike" / "samples"
EXT = SRC / "external"
DEST = ROOT / "public" / "samples"
NAMES = ["mystery_" + c for c in "abcdefghi"] + ["external_a", "external_b"]


def source_of(name: str) -> Path:
    return (EXT if name.startswith("external_") else SRC) / name


def pillow_provenance() -> str:
    m = re.search(r"Tool: Pillow ([0-9][0-9.]*)", (EXT / "README.md").read_text(encoding="utf-8"))
    return f"written by Pillow {m.group(1)}" if m else "written by Pillow"


def build_index() -> list:
    index = []
    for name in NAMES:
        entry = {"name": name, "size": source_of(name).stat().st_size}
        if name.startswith("external_"):
            entry["provenance"] = pillow_provenance()
        index.append(entry)
    return index


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        shutil.copyfile(source_of(name), DEST / name)
    (DEST / "index.json").write_text(json.dumps(build_index(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"copied {len(NAMES)} samples to {DEST}")


if __name__ == "__main__":
    main()