"""Every steering file in .kiro/steering applies to something.

An `always` file applies everywhere. A `fileMatch` file applies only when a file matching its pattern is in play,
so each pattern must match at least one tracked file. Until 25 Nov 2026 ui.md matched `necropsy/ui/**`, a path that
never existed, and so never applied; this test keeps that from happening again. Added by Claude Code.
"""
import fnmatch
import json
import subprocess

import pytest

from tests.conftest import REPO_ROOT

STEERING = sorted((REPO_ROOT / ".kiro" / "steering").glob("*.md"))


def front_matter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") or text.startswith("---\r\n"), f"{path.name}: no front matter"
    body = text.split("---", 2)[1]
    meta = {}
    for line in body.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def patterns(value):
    value = value.strip()
    if value.startswith("["):
        return json.loads(value)
    return [value.strip("\"'")]


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def test_there_are_five_steering_files():
    assert [p.name for p in STEERING] == ["engine.md", "parsers.md", "project.md", "tests.md", "ui.md"]


@pytest.mark.parametrize("path", STEERING, ids=lambda p: p.name)
def test_each_steering_file_applies_to_something(path):
    meta = front_matter(path)
    assert meta.get("inclusion") in {"always", "fileMatch", "manual"}, meta
    if meta["inclusion"] != "fileMatch":
        return
    files = tracked_files()
    for pat in patterns(meta["fileMatchPattern"]):
        hits = [f for f in files if fnmatch.fnmatch(f, pat)]
        assert hits, f"{path.name}: fileMatchPattern {pat!r} matches no tracked file, so the file never applies"
