"""public/samples/ is a byte-identical copy of the source samples, and the index never carries an outcome."""
import json

import pytest

from tests.conftest import REPO_ROOT
from tools import copy_samples as cs

PUBLIC = REPO_ROOT / "public" / "samples"


def test_there_are_nine_corpus_samples_then_the_external_ones():
    names = [e["name"] for e in json.loads((PUBLIC / "index.json").read_text(encoding="utf-8"))]
    assert names == ["mystery_" + c for c in "abcdefghi"] + ["external_a", "external_b"]


@pytest.mark.parametrize("name", cs.NAMES)
def test_public_copy_is_byte_identical_to_source(name):
    assert (PUBLIC / name).read_bytes() == cs.source_of(name).read_bytes()


def test_index_matches_the_generator_and_has_only_name_size_provenance():
    on_disk = json.loads((PUBLIC / "index.json").read_text(encoding="utf-8"))
    assert on_disk == cs.build_index()
    for e in on_disk:
        assert set(e) <= {"name", "size", "provenance"}
        assert e["size"] == (PUBLIC / e["name"]).stat().st_size
        assert ("provenance" in e) == e["name"].startswith("external_")
    text = (PUBLIC / "index.json").read_text(encoding="utf-8").lower()
    for word in ("resolved", "ambiguity", "failed", "corpus", "demo", "pcx", "tga", "tiff", "pbm"):
        assert word not in text
    assert all(e["provenance"].startswith("written by Pillow ") for e in on_disk if "provenance" in e)