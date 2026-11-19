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


# =====================================================================
# Task 7.4: Engine unit tests
# =====================================================================

import dataclasses as _dc  # noqa: E402

import necropsy.engine.engine as engine_mod  # noqa: E402
from necropsy.engine import Engine  # noqa: E402
from necropsy.engine.budget import Budget as RealBudget  # noqa: E402
from necropsy.engine.closure import check_closure as real_check_closure  # noqa: E402
from necropsy.engine.probes import ProbeOutcome  # noqa: E402
from necropsy.engine.strategies import STRATEGIES as REAL_STRATEGIES  # noqa: E402
from tests.conftest import corpus_bytes  # noqa: E402


class StepClock:
    """Each call returns 10 more than the last; any deadline <= 5 s passes on the next call."""

    def __init__(self) -> None:
        self.t = -10.0

    def __call__(self) -> float:
        self.t += 10.0
        return self.t


def _seed(width, height, header, probe="tga", **kw) -> Hypothesis:
    return Hypothesis(width, height, 8, header, probe_name=probe, **kw)


# 32 zero bytes: a 16-byte header plus 16 data bytes; 4x4 and 2x8 at 8 bpp both close.
_BLOB = bytes(32)


def _probe_returning(seed):
    return lambda data: ProbeOutcome(seed, ())


# ---- Req 5.8: input_too_short ----

@pytest.mark.parametrize("data", [b"", b"\x0a\x00"])
def test_short_input_fails_with_one_entry(data):
    r = Engine().run(data)
    assert r.status == "FAILED"
    assert r.termination == "input_too_short"
    assert len(r.rejections) == 1
    assert r.rejections[0].reason == "input_too_short"


# ---- Req 6.1: internal_error ----

def test_probe_exception_gives_internal_error(monkeypatch):
    def boom(data):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(engine_mod, "PROBES", (("boom", boom),))
    r = Engine().run(_BLOB)
    assert r.status == "FAILED"
    assert r.termination == "internal_error"
    assert len(r.rejections) == 1
    assert r.rejections[0].reason == "internal_error"
    assert r.rejections[0].detail.startswith("RuntimeError")


# ---- Req 5.2: deadline ----

def test_deadline_exceeded_on_mystery_c():
    r = Engine(deadline_seconds=5.0, clock=StepClock()).run(corpus_bytes("mystery_c"))
    assert r.status == "FAILED"
    assert r.termination == "deadline_exceeded"


# ---- Req 5.3: cap ----

def test_cap_of_one_on_mystery_h(monkeypatch):
    def capped(deadline_seconds, cap=10_000, clock=None, **kw):
        args = {"clock": clock} if clock is not None else {}
        return RealBudget(deadline_seconds, cap=1, **args)

    monkeypatch.setattr(engine_mod, "Budget", capped)
    r = Engine().run(corpus_bytes("mystery_h"))
    assert r.status == "FAILED"
    assert r.termination == "search_cap_exceeded"
    assert r.total_checks <= 1


# ---- Req 2.9, 10.3: collect-all in the probe phase ----

def test_probe_phase_collects_all_closers(monkeypatch):
    a, b = _seed(4, 4, 16), _seed(2, 8, 16)
    monkeypatch.setattr(engine_mod, "PROBES", (("pa", _probe_returning(a)), ("pb", _probe_returning(b))))
    r = Engine().run(_BLOB)
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "probe"
    assert [hypothesis_key(c.hypothesis) for c in r.candidates] == [hypothesis_key(a), hypothesis_key(b)]


# ---- Req 3.4-3.6: collect-all in the revision phase ----

def _strat(name, **change):
    def fn(h):
        return (_dc.replace(h, revision_path=h.revision_path + (name,), **change),)
    return fn


def test_revision_phase_collects_all_closers_and_order_is_irrelevant(monkeypatch):
    seed = _seed(3, 3, 16)  # 9 bytes vs 16 available: does not close
    monkeypatch.setattr(engine_mod, "PROBES", (("pa", _probe_returning(seed)),))
    s1 = ("s1", _strat("s1", width=4, height=4))
    s2 = ("s2", _strat("s2", width=2, height=8))

    monkeypatch.setattr(engine_mod, "STRATEGIES", (s1, s2))
    r1 = Engine().run(_BLOB)
    monkeypatch.setattr(engine_mod, "STRATEGIES", (s2, s1))
    r2 = Engine().run(_BLOB)

    for r in (r1, r2):
        assert r.status == "UNRESOLVED_AMBIGUITY"
        assert r.stage == "revision"
    keys1 = {hypothesis_key(c.hypothesis) for c in r1.candidates}
    keys2 = {hypothesis_key(c.hypothesis) for c in r2.candidates}
    assert keys1 == keys2 and len(keys1) == 2


# ---- Req 3.2, 3.6, 3.9, 3.10: alternative paths ----

def test_alternative_paths_on_mystery_h():
    r = Engine().run(corpus_bytes("mystery_h"))
    assert r.status == "RESOLVED"
    c = r.candidate
    canonical = ("inclusive_bounds", "row_padding_variants")
    alt = ("row_padding_variants", "inclusive_bounds")
    assert c.hypothesis.revision_path == canonical
    assert alt in c.alternative_paths
    assert canonical not in c.alternative_paths


def test_reversed_strategies_swap_canonical_and_alternative(monkeypatch):
    data = corpus_bytes("mystery_h")
    fwd = Engine().run(data).candidate
    monkeypatch.setattr(engine_mod, "STRATEGIES", tuple(reversed(REAL_STRATEGIES)))
    r = Engine().run(data)
    assert r.status == "RESOLVED"
    rev = r.candidate
    assert hypothesis_key(rev.hypothesis) == hypothesis_key(fwd.hypothesis)
    assert rev.hypothesis.revision_path == ("row_padding_variants", "inclusive_bounds")
    assert ("inclusive_bounds", "row_padding_variants") in rev.alternative_paths
    assert {fwd.hypothesis.revision_path, *fwd.alternative_paths} == \
        {rev.hypothesis.revision_path, *rev.alternative_paths}


# ---- Req 3.3: dedup ----

def test_no_key_checked_twice_on_mystery_h(monkeypatch):
    seen = []

    def spy(h, data):
        seen.append(hypothesis_key(h))
        return real_check_closure(h, data)

    monkeypatch.setattr(engine_mod, "check_closure", spy)
    Engine().run(corpus_bytes("mystery_h"))
    assert seen
    assert len(seen) == len(set(seen))


# ---- Req 5.9: rejection order ----

def test_rejections_are_probe_then_revision():
    r = Engine().run(corpus_bytes("mystery_h"))
    sources = [e.source for e in r.rejections]
    is_rev = [s.startswith("revision:") for s in sources]
    assert any(is_rev) and not all(is_rev)
    first_rev = is_rev.index(True)
    assert not any(is_rev[:first_rev]) and all(is_rev[first_rev:])
    assert sources[0] == "pcx"


# ---- Req 5.10: partial candidates ----

def test_winner_before_deadline_stop_is_partial_candidate(monkeypatch):
    a, b = _seed(4, 4, 16), _seed(2, 8, 16)
    monkeypatch.setattr(engine_mod, "PROBES", (("pa", _probe_returning(a)), ("pb", _probe_returning(b))))
    state = {"expired": False}

    def clock():
        return 1000.0 if state["expired"] else 0.0

    def coherence(decoded, height, stride):
        state["expired"] = True  # the deadline passes once the first winner is scored
        return None, "unscorable"

    monkeypatch.setattr(engine_mod, "row_coherence", coherence)
    r = Engine(deadline_seconds=5.0, clock=clock).run(_BLOB)
    assert r.status == "FAILED"
    assert r.termination == "deadline_exceeded"
    # Req 5.10: every candidate that closed before termination is listed (a closed
    # before the stop; b may also have closed before the stop was observed).
    keys = [hypothesis_key(c.hypothesis) for c in r.partial_candidates]
    assert hypothesis_key(a) in keys
