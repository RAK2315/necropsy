"""Shared pytest configuration: sys.path setup and the sample corpus."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "spike" / "samples"
CORPUS_NAMES = tuple("mystery_" + c for c in "abcdefghi")

for _p in (str(REPO_ROOT), str(REPO_ROOT / "spike")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def corpus_bytes(name: str) -> bytes:
    """Return the bytes of one corpus file, e.g. corpus_bytes("mystery_a")."""
    return (SAMPLES_DIR / name).read_bytes()


@pytest.fixture
def corpus() -> dict:
    """Map file name (mystery_a to mystery_i) to its bytes."""
    return {name: corpus_bytes(name) for name in CORPUS_NAMES}
