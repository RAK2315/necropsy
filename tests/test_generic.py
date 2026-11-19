"""Unit tests for Generic Search (task 6.2).

Expected values come from requirements.md (Req 4, 5, 7.4/7.6/7.7) and
design.md "Generic Search" / "Corpus Trace (measured)".
"""
import struct

from necropsy.engine.budget import Budget
from necropsy.engine.closure import check_closure
from necropsy.engine.generic import (
    HEADER_LENGTHS,
    VALID_BIT_DEPTHS,
    WIDTH_HEIGHT_FORMATS,
    GenericOutcome,
    generic_search,
)
from necropsy.engine.types import hypothesis_key
from tests.conftest import corpus_bytes

FAR = 1e9


def _run(name, budget=None):
    data = corpus_bytes(name)
    budget = budget or Budget(FAR)
    rejected = []
    out = generic_search(data, budget, lambda h, v: rejected.append((h, v)))
    return data, out, budget


def _keys(out):
    return [hypothesis_key(h) for h, _ in out.found]


def _find(out, key):
    for h, _ in out.found:
        if hypothesis_key(h) == key:
            return h
    return None


def test_mystery_d_found_set():
    # Req 7.4 and design Corpus Trace: 18 closers, includes 8x8 8bpp header 40
    _, out, _ = _run("mystery_d")
    assert isinstance(out, GenericOutcome)
    assert out.stop is None
    assert (8, 8, 8, 40, 1, "none", None) in _keys(out)
    assert len(out.found) == 18


def test_mystery_f_found_set_and_equivalent_reads():
    # Req 7.6: includes 12x10 8bpp header 12; 8 entries (design Corpus Trace)
    _, out, _ = _run("mystery_f")
    assert out.stop is None
    key = (12, 10, 8, 12, 1, "none", None)
    assert key in _keys(out)
    assert len(out.found) == 8
    h = _find(out, key)
    at0 = [r for r in h.fields if r.name == "width" and r.offset == 0]
    fmts = {r.fmt for r in at0}
    assert len(fmts & {"<H", "<I", "<i"}) >= 2
    assert all(r.value == (12,) for r in at0)


def test_mystery_g_found_set():
    # Req 7.7: includes 8x8 24bpp header 20; 8 entries (design Corpus Trace)
    _, out, _ = _run("mystery_g")
    assert out.stop is None
    assert (8, 8, 24, 20, 1, "none", None) in _keys(out)
    assert len(out.found) == 8


def test_deterministic_ordered_results():
    # Req 4 / design: enumeration order is deterministic
    _, a, _ = _run("mystery_d")
    _, b, _ = _run("mystery_d")
    assert _keys(a) == _keys(b)
    assert [h for h, _ in a.found] == [h for h, _ in b.found]


def test_cap_of_three_stops_after_three_checks():
    # Req 5.3: shared cap; a further check returns search_cap_exceeded
    _, out, budget = _run("mystery_d", Budget(FAR, cap=3))
    assert out.stop == "search_cap_exceeded"
    assert budget.checks == 3


def test_deadline_already_passed_stops_before_any_check():
    # Req 5.1: deadline checked at start of each header length
    _, out, budget = _run("mystery_d", Budget(-1.0))
    assert out.stop == "deadline_exceeded"
    assert budget.checks == 0
    assert out.found == ()


def test_injected_clock_past_deadline():
    # Req 5.1 with an injected clock that jumps past the deadline
    t = [0.0]
    budget = Budget(5.0, clock=lambda: t[0])
    t[0] = 100.0
    _, out, _ = _run("mystery_d", budget)
    assert out.stop == "deadline_exceeded"
    assert budget.checks == 0


def test_header_lengths_req_4_2():
    assert HEADER_LENGTHS == tuple(range(4, 257, 4))
    assert HEADER_LENGTHS[0] == 4 and HEADER_LENGTHS[-1] == 256


def test_axes_constants():
    # Req 4.3, 4.4
    assert set(WIDTH_HEIGHT_FORMATS) == {"<H", ">H", "<I", ">I", "<i", ">i"}
    assert tuple(VALID_BIT_DEPTHS) == (1, 4, 8, 16, 24, 32)


def test_found_candidates_close_and_fields_round_trip():
    # Req 8.2 and Req 1: every found candidate closes; every FieldRecord round-trips
    for name in ("mystery_d", "mystery_f", "mystery_g"):
        data, out, _ = _run(name)
        for h, _v in out.found:
            assert check_closure(h, data).ok
            for r in h.fields:
                assert struct.unpack_from(r.fmt, data, r.offset) == r.value


# --- Task 6.3: Generic Search never raises and respects the cap ---
from hypothesis import example, given, settings
from hypothesis import strategies as st

from tests.support.inputs import engine_inputs

CAP = 10_000


def _check_generic_invariants(data):
    budget = Budget(FAR, cap=CAP)
    out = generic_search(data, budget, lambda h, v: None)
    assert isinstance(out, GenericOutcome)
    assert budget.checks <= CAP  # Req 5.3
    for h, _v in out.found:
        assert check_closure(h, data).ok  # Req 8.2
        by_name = {}
        for r in h.fields:
            by_name.setdefault(r.name, r.value)
            assert r.value == by_name[r.name]  # Property 5
            assert struct.unpack_from(r.fmt, data, r.offset) == r.value


# Feature: structure-inference-engine, Generic search never raises
# **Validates: Requirements 4.8, 5.3, 6.4, 6.7**
@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=65536))
def test_generic_search_never_raises_arbitrary_bytes(data):
    _check_generic_invariants(data)


# Feature: structure-inference-engine, Generic search never raises
# **Validates: Requirements 4.8, 5.3, 6.4, 6.7**
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
@example(corpus_bytes("mystery_d"))
@example(corpus_bytes("mystery_f"))
@example(corpus_bytes("mystery_g"))
def test_generic_search_never_raises_mutated_corpus(data):
    _check_generic_invariants(data)