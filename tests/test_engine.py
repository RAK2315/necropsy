"""Unit tests for engine types and budget (task 1.4)."""

from __future__ import annotations

import dataclasses

import pytest

from necropsy.engine.budget import Budget
from necropsy.engine.types import (
    AmbiguousResult,
    Candidate,
    FailureReport,
    FieldRecord,
    Hypothesis,
    RejectionEntry,
    VerifiedHypothesis,
    hypothesis_key,
)


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _hyp(**kw) -> Hypothesis:
    base = dict(width=4, height=3, bit_depth=8, header_size=16)
    base.update(kw)
    return Hypothesis(**base)


def _candidate() -> Candidate:
    return Candidate(
        hypothesis=_hyp(), row_stride=4, expected_decoded_bytes=12,
        data_start=16, data_end=28, trailer=None,
        coherence_score=None, coherence_status="not_computed",
    )


# ---- types ----

def test_hypothesis_key_is_exactly_the_seven_fields():
    h = _hyp(row_alignment=2, encoding="rle_pcx", data_end=99)
    assert hypothesis_key(h) == (4, 3, 8, 16, 2, "rle_pcx", 99)


def test_hypothesis_key_ignores_other_fields():
    a = _hyp()
    b = _hyp(
        fields=(FieldRecord("w", 0, "<H", (4,)),),
        probe_name="pcx",
        bounds=(0, 0, 3, 2),
        revision_path=("inclusive_bounds",),
    )
    assert hypothesis_key(a) == hypothesis_key(b)


@pytest.mark.parametrize("field_name,value", [
    ("width", 5), ("height", 4), ("bit_depth", 1), ("header_size", 17),
    ("row_alignment", 4), ("encoding", "rle_pcx"), ("data_end", 7),
])
def test_hypothesis_key_changes_with_each_key_field(field_name, value):
    assert hypothesis_key(_hyp()) != hypothesis_key(_hyp(**{field_name: value}))


def test_default_statuses():
    v = VerifiedHypothesis(_candidate(), "probe", (), 1, 28)
    a = AmbiguousResult((_candidate(), _candidate()), "generic", "r", None, (), 2, 28)
    f = FailureReport("exhausted", (), 0, 28)
    assert v.status == "RESOLVED"
    assert a.status == "UNRESOLVED_AMBIGUITY"
    assert f.status == "FAILED"


def test_result_types_are_frozen():
    v = VerifiedHypothesis(_candidate(), "probe", (), 1, 28)
    a = AmbiguousResult((_candidate(), _candidate()), "generic", "r", None, (), 2, 28)
    f = FailureReport("exhausted", (), 0, 28)
    for obj, name in ((v, "status"), (a, "status"), (f, "termination")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, name, "x")


def test_other_types_are_frozen():
    for obj, name in (
        (_hyp(), "width"),
        (FieldRecord("w", 0, "<H", (4,)), "name"),
        (_candidate(), "row_stride"),
        (RejectionEntry("arithmetic_mismatch", "pcx"), "reason"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, name, None)


# ---- budget ----

def test_deadline_fires_at_exactly_deadline_seconds():
    clock = FakeClock(100.0)
    b = Budget(5.0, clock=clock)
    assert b.stop_reason() is None
    clock.now = 104.999
    assert b.stop_reason() is None
    clock.now = 105.0
    assert b.stop_reason() == "deadline_exceeded"
    clock.now = 200.0
    assert b.stop_reason() == "deadline_exceeded"


def test_charge_returns_deadline_and_does_not_count():
    clock = FakeClock(0.0)
    b = Budget(1.0, clock=clock)
    assert b.charge() is None
    assert b.checks == 1
    clock.now = 1.0
    assert b.charge() == "deadline_exceeded"
    assert b.checks == 1


def test_cap_fires_after_10000_charges():
    b = Budget(5.0, clock=FakeClock())
    assert b.cap == 10_000
    for _ in range(10_000):
        assert b.charge() is None
    assert b.checks == 10_000
    assert b.stop_reason() == "search_cap_exceeded"
    assert b.charge() == "search_cap_exceeded"


def test_checks_never_exceeds_cap():
    b = Budget(5.0, cap=10_000, clock=FakeClock())
    for _ in range(10_050):
        b.charge()
    assert b.checks == 10_000


def test_deadline_wins_when_both_apply():
    clock = FakeClock(0.0)
    b = Budget(1.0, cap=3, clock=clock)
    for _ in range(3):
        assert b.charge() is None
    assert b.stop_reason() == "search_cap_exceeded"
    clock.now = 1.0
    assert b.stop_reason() == "deadline_exceeded"
    assert b.charge() == "deadline_exceeded"
    assert b.checks == 3
