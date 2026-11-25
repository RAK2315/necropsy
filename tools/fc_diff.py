"""Format-coverage diff tool (format-coverage spec, Requirement 20.1 and 20.2).

Runs the engine over the 11 samples (spike/samples/mystery_*, spike/samples/external/external_*)
and the 81 corpus files (spike/samples/real/, in manifest order). For each file it records
status, termination, and for every candidate its hypothesis key and data region. It compares
that with spike/fc_baseline.json and prints every difference. Check counts and rejection
counts are not compared.

Run:  python -m tools.fc_diff             compare with the baseline, exit 1 on any difference
      python -m tools.fc_diff --write     write spike/fc_baseline.json (only before an engine change)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "spike" / "samples"
REAL = SAMPLES / "real"
BASELINE = ROOT / "spike" / "fc_baseline.json"


def sample_paths() -> list[tuple[str, Path]]:
    paths = sorted(p for p in SAMPLES.glob("mystery_*") if p.is_file())
    paths += sorted(p for p in (SAMPLES / "external").glob("external_*") if p.is_file())
    return [(f"samples/{p.name}", p) for p in paths]


def corpus_paths() -> list[tuple[str, Path]]:
    manifest = json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))["files"]
    return [(f"real/{e['file']}", REAL / e["file"]) for e in manifest]


def _jsonable(x):
    if isinstance(x, (tuple, list)):
        return [_jsonable(i) for i in x]
    return x


def measure_one(data: bytes) -> dict:
    from necropsy.engine import Engine
    from necropsy.engine.types import hypothesis_key

    result = Engine().run(data)
    cands = [result.candidate] if result.status == "RESOLVED" else list(getattr(result, "candidates", ()))
    return {
        "status": result.status,
        "termination": getattr(result, "termination", None),
        "candidates": [
            {"key": _jsonable(hypothesis_key(c.hypothesis)), "region": [c.data_start, c.data_end]}
            for c in cands
        ],
    }


def measure() -> dict:
    return {name: measure_one(path.read_bytes()) for name, path in sample_paths() + corpus_paths()}


def diff(old: dict, new: dict) -> list[str]:
    lines: list[str] = []
    for name in sorted(set(old) | set(new)):
        if name not in old:
            lines.append(f"{name}: not in baseline")
        elif name not in new:
            lines.append(f"{name}: in baseline, not measured")
        else:
            for field in ("status", "termination", "candidates"):
                if old[name][field] != new[name][field]:
                    lines.append(f"{name}: {field}: {old[name][field]!r} -> {new[name][field]!r}")
    return lines


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT))
    new = measure()
    if "--write" in argv:
        BASELINE.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE.name}: {len(new)} files")
        return 0
    old = json.loads(BASELINE.read_text(encoding="utf-8"))
    lines = diff(old, new)
    for line in lines:
        print(line)
    print(f"{len(new)} files measured, {len(lines)} differences")
    return 1 if lines else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
