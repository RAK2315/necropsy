"""The committed format-coverage baseline equals a live engine run (format-coverage Requirement 20.1, 20.2).

Until a task changes engine behaviour on purpose, this test holds. A task that moves files
updates spike/fc_baseline.json in the same commit, with the diff stated in its message.
"""
import json

from tools import fc_diff


def test_baseline_covers_11_samples_and_81_corpus_files():
    baseline = json.loads(fc_diff.BASELINE.read_text(encoding="utf-8"))
    assert sum(k.startswith("samples/") for k in baseline) == 11
    assert sum(k.startswith("real/") for k in baseline) == 81


def test_baseline_equals_live_run():
    baseline = json.loads(fc_diff.BASELINE.read_text(encoding="utf-8"))
    assert fc_diff.diff(baseline, fc_diff.measure()) == []
