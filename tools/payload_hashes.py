"""SHA-256 of the serialised payload of every sample (engine_ms zeroed). Used by the Task 2 test
and to take the hashes on the code before a data-model change.
Run:  python -m tools.payload_hashes [out.json]"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

from necropsy.engine import Engine
from tools import fc_diff
from web.serialise import to_payload


def measure() -> dict:
    out = {}
    for name, path in fc_diff.sample_paths():
        data = path.read_bytes()
        payload = to_payload(Engine().run(data), data, 0.0)
        payload["engine_ms"] = 0.0
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        out[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return out


if __name__ == "__main__":
    result = measure()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(len(result), "payloads")
