"""Write tests/data/tiff_single_strip_fields.json from the probe as it stood before task 18.

Usage: git show a42a573:necropsy/engine/probes.py > necropsy/engine/probes_old.py
       python -m tools.snapshot_tiff_fields ; delete probes_old.py afterwards.
"""
import json
from pathlib import Path

from necropsy.engine import probes_old
from tools import real_corpus as rc


def rows(probe, data):
    out = probe(data)
    return None if out is None else [[f.name, f.offset, f.fmt, repr(f.value)] for f in out.seed.fields]


def main():
    snap = {}
    for p in sorted(rc.REAL.iterdir()):
        if not p.is_file():
            continue
        data = p.read_bytes()
        old = rows(probes_old.probe_tiff, data)
        if old is None:
            continue
        if any(r[0] == "strip_offset[0]" for r in old):
            continue  # multi-strip
        snap[p.name] = old
    out = Path(__file__).resolve().parent.parent / "tests" / "data" / "tiff_single_strip_fields.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(snap, indent=1, sort_keys=True))
    print(len(snap), file=open("build/snap.txt", "w"))


if __name__ == "__main__":
    main()
