"""Copy the sample files into public/samples/ and write samples/index.json.

The index holds name, size, one plain line saying what the engine finds in the sample, and, for samples
NECROPSY did not make, a provenance line. The line is computed here from a fresh engine run, so it cannot
drift from the engine. Wording follows the glossary in public/js/words.js: translate what the engine found,
never what it implies about the file.

The real-world sample (from Pillow's test suite, MIT-CMU) is checked against the corpus manifest's sha256,
and its licence notice is copied beside it, because MIT-CMU requires the notice in supporting documentation.

Run from anywhere: python tools/copy_samples.py
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "spike" / "samples"
EXT = SRC / "external"
REAL = SRC / "real"
DEST = ROOT / "public" / "samples"
REAL_SAMPLE = "pillow_odd_stride.pcx"
LICENCE = "Pillow-MIT-CMU.txt"
NAMES = ["mystery_" + c for c in "abcdefghi"] + ["external_a", "external_b", REAL_SAMPLE]


def source_of(name: str) -> Path:
    if name == REAL_SAMPLE:
        return REAL / name
    return (EXT if name.startswith("external_") else SRC) / name


def pillow_provenance() -> str:
    import re
    m = re.search(r"Tool: Pillow ([0-9][0-9.]*)", (EXT / "README.md").read_text(encoding="utf-8"))
    return f"written by Pillow {m.group(1)}" if m else "written by Pillow"


def manifest_sha256(name: str) -> str:
    files = json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))["files"]
    return next(f["sha256"] for f in files if f["file"] == name)


# Plain words for each revision step (strategies.py). Same wording as public/js/words.js CORRECTION.
def _correction(step: str, cand) -> str:
    if step == "inclusive_bounds":          # strategies.inclusive_bounds: width = xmax - xmin + 1, height likewise
        return "the header's bounds are counted inclusively"
    if step == "rle_pcx":                   # strategies.rle_pcx: encoding none -> rle_pcx
        return "the data is run-length decoded"
    if step == "row_padding_variants":      # strategies.row_padding_variants: row_alignment 2 or 4
        return f"rows are padded to a multiple of {cand.row_alignment} bytes"
    return step


def describe(data: bytes) -> str:
    """One plain line from a fresh engine run: what the engine found, nothing more."""
    from necropsy.engine import Engine
    r = Engine(deadline_seconds=5.0).run(data)
    if r.status == "RESOLVED":
        h = r.candidate.hypothesis
        size = f"{h.width} × {h.height}, {h.bit_depth}-bit"
        steps = [_correction(s, h) for s in h.revision_path]
        if h.probe_name == "generic":
            return f"No format signature matched. One headerless layout fits: {size}."
        if not steps:
            return f"One reading fits: {size}, as the header declares."
        return f"One reading fits: {size}, once " + " and ".join(steps) + "."
    if r.status == "UNRESOLVED_AMBIGUITY":
        return f"{len(r.candidates)} readings fit exactly. NECROPSY does not choose."
    return "Not recovered: no layout tried fits the data exactly."


def build_index() -> list:
    index = []
    for name in NAMES:
        src = source_of(name)
        entry = {"name": name, "size": src.stat().st_size, "description": describe(src.read_bytes())}
        if name.startswith("external_"):
            entry["provenance"] = pillow_provenance()
        if name == REAL_SAMPLE:
            entry["provenance"] = "from Pillow's test suite (MIT-CMU)"
            entry["licence"] = "LICENSES/" + LICENCE
        index.append(entry)
    return index


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    got = hashlib.sha256(source_of(REAL_SAMPLE).read_bytes()).hexdigest()
    if got != manifest_sha256(REAL_SAMPLE):
        raise SystemExit(f"{REAL_SAMPLE}: sha256 {got} does not match the corpus manifest")
    for name in NAMES:
        shutil.copyfile(source_of(name), DEST / name)
    (DEST / "LICENSES").mkdir(exist_ok=True)
    shutil.copyfile(REAL / "LICENSES" / LICENCE, DEST / "LICENSES" / LICENCE)
    (DEST / "index.json").write_text(json.dumps(build_index(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"copied {len(NAMES)} samples and the {LICENCE} notice to {DEST}")


if __name__ == "__main__":
    main()
