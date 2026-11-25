"""Copy the sample files into public/samples/ and write samples/index.json.

The index holds name, size, one plain line saying what the engine finds in the sample, and, for samples
NECROPSY did not make, a provenance line. The line is computed here from a fresh engine run, so it cannot
drift from the engine. Wording follows the glossary in public/js/words.js: translate what the engine found,
never what it implies about the file.

The real-world samples (from Pillow's and ImageMagick's test suites) are checked against the corpus manifest's
sha256, and each one's licence notice is copied beside it, because both licences require the notice to travel with
the file. UI task 38 (Rehaan, 25 Nov): three real pictures, a photograph, a portrait scan and a signature, are listed
first, so the demo shows real images rather than the corpus's few-pixel test files.

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
REAL_SAMPLE = "pillow_odd_stride.pcx"     # the primary action's file
LICENCE = "Pillow-MIT-CMU.txt"
# real files from the corpus (spike/samples/real/): name -> (provenance, licence notice in spike/samples/real/LICENSES/)
REAL_SAMPLES = {
    "imagemagick_input.tga": ("from ImageMagick's test suite (ImageMagick License)", "ImageMagick-License.txt"),
    "pillow_hopper_1bit.pbm": ("from Pillow's test suite (MIT-CMU)", LICENCE),
    "pillow_pil184.pcx": ("from Pillow's test suite (MIT-CMU)", LICENCE),
    REAL_SAMPLE: ("from Pillow's test suite (MIT-CMU)", LICENCE),
}
PICTURES = ["imagemagick_input.tga", "pillow_hopper_1bit.pbm", "pillow_pil184.pcx"]
NAMES = PICTURES + ["mystery_" + c for c in "abcdefghi"] + ["external_a", "external_b", REAL_SAMPLE]


def source_of(name: str) -> Path:
    if name in REAL_SAMPLES:
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
        if name in REAL_SAMPLES:
            entry["provenance"], lic = REAL_SAMPLES[name]
            entry["licence"] = "LICENSES/" + lic
        index.append(entry)
    return index


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name in REAL_SAMPLES:
        got = hashlib.sha256(source_of(name).read_bytes()).hexdigest()
        if got != manifest_sha256(name):
            raise SystemExit(f"{name}: sha256 {got} does not match the corpus manifest")
    for name in NAMES:
        shutil.copyfile(source_of(name), DEST / name)
    (DEST / "LICENSES").mkdir(exist_ok=True)
    for lic in sorted({lic for _, lic in REAL_SAMPLES.values()}):
        shutil.copyfile(REAL / "LICENSES" / lic, DEST / "LICENSES" / lic)
    (DEST / "index.json").write_text(json.dumps(build_index(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"copied {len(NAMES)} samples and their licence notices to {DEST}")


if __name__ == "__main__":
    main()
