"""The spec panel's claim: the files it displays and the ZIP it downloads are byte-identical to the emitter's output.

Runs the real page in headless Edge or Chrome against the real app on a local port. A stale cache, a truncating
renderer or a placeholder would pass a screenshot; it does not pass this.
"""
import base64
import io
import json
import subprocess
import zipfile

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import REPO_ROOT, corpus_bytes

PROBE = REPO_ROOT / "tools" / "panel_probe.mjs"


def probe(base_url, sample):
    out = subprocess.run(["node", str(PROBE), base_url, sample], capture_output=True, text=True,
                         encoding="utf-8", timeout=90)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    if result.get("error") == "no browser":
        pytest.skip("no Edge or Chrome found to drive")
    assert "error" not in result, result
    return result


@pytest.mark.parametrize("sample", ["mystery_e", "mystery_d"])
def test_panel_text_and_zip_are_byte_identical_to_the_emitter(base_url, sample):
    data = corpus_bytes(sample)
    spec = emit_spec(Engine().run(data), data)
    expected = {name: text.encode("utf-8") for name, text in spec.files}
    assert len(expected) == 3

    got = probe(base_url, sample)

    # what the panel displays
    assert got["folder"] == f"{spec.slug}/"
    assert list(got["files"]) == [name for name, _ in spec.files]
    for name, text in got["files"].items():
        assert text.encode("utf-8") == expected[name], f"displayed {name} differs from the emitter's output"

    # what the panel downloads
    assert got["zip_type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(got["zip_b64"])))
    assert sorted(z.namelist()) == sorted(f"{spec.slug}/{name}" for name in expected)
    for name, raw in expected.items():
        assert z.read(f"{spec.slug}/{name}") == raw, f"zipped {name} differs from the emitter's output"