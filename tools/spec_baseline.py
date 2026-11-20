"""Record the emitted spec text of every file under spike/samples/ as JSON.

Usage: python tools/spec_baseline.py OUT.json
Each entry maps a sample path to its emitted files, or to the structured error
the emitter or engine returned. Used by task 22 to prove only mystery_i changes.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from necropsy.emit import emit_spec  # noqa: E402
from necropsy.engine import Engine  # noqa: E402

SAMPLES = ROOT / "spike" / "samples"


def sample_paths():
    return sorted(p for p in SAMPLES.rglob("*") if p.is_file())


def record(path: Path) -> dict:
    data = path.read_bytes()
    try:
        spec = emit_spec(Engine().run(data), data)
    except Exception as exc:  # recorded, so the baseline shows it
        return {"raised": repr(exc)}
    if hasattr(spec, "files"):
        return {"slug": spec.slug, "files": dict(spec.files)}
    return {"error": getattr(spec, "message", repr(spec))}


def main(argv) -> int:
    out = {p.relative_to(SAMPLES).as_posix(): record(p) for p in sample_paths()}
    Path(argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(len(out), "samples recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
