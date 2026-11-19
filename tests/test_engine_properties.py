"""Engine-level property tests: Properties 1 to 5."""
import struct
import time

from hypothesis import example, given, settings

from necropsy.engine import (
    AmbiguousResult, Engine, FailureReport, VerifiedHypothesis,
)
from necropsy.engine.closure import check_closure
from tests.conftest import CORPUS_NAMES, corpus_bytes
from tests.support.inputs import engine_inputs

RESULT_TYPES = (VerifiedHypothesis, AmbiguousResult, FailureReport)


def _with_corpus_examples(test):
    for name in CORPUS_NAMES:
        test = example(corpus_bytes(name))(test)
    return test


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_never_raises(data):
    """Feature: structure-inference-engine, Property 1: Never raises

    **Validates: Requirements 6.2, 6.3, 6.5**
    """
    assert isinstance(Engine().run(data), RESULT_TYPES)


@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_deadline_bound(data):
    """Feature: structure-inference-engine, Property 2: Deadline bound

    **Validates: Requirements 5.4, 6.6**
    """
    start = time.monotonic()
    result = Engine(deadline_seconds=5.0).run(data)
    elapsed = time.monotonic() - start
    assert isinstance(result, RESULT_TYPES)
    # 5.0 s deadline plus the 0.25 s margin allowed by Req 5.4.
    assert elapsed < 5.25


def _candidates(result):
    """Candidates of a RESOLVED or UNRESOLVED_AMBIGUITY result; empty otherwise."""
    if isinstance(result, VerifiedHypothesis):
        return (result.candidate,)
    if isinstance(result, AmbiguousResult):
        return result.candidates
    return ()


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_closure_soundness(data):
    """Feature: structure-inference-engine, Property 3: Closure soundness

    **Validates: Requirements 1.7, 1.8, 1.14, 10.2, 10.3**
    """
    for cand in _candidates(Engine().run(data)):
        verdict = check_closure(cand.hypothesis, data)
        assert verdict.ok
        assert verdict.data_start == cand.data_start
        assert verdict.data_end == cand.data_end
        assert verdict.decoded == cand.decoded


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_field_round_trip(data):
    """Feature: structure-inference-engine, Property 4: Field round-trip

    **Validates: Requirements 8.1, 8.2**
    """
    for cand in _candidates(Engine().run(data)):
        for fr in cand.hypothesis.fields:
            assert struct.unpack_from(fr.fmt, data, fr.offset) == fr.value


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_equivalent_reads_agree(data):
    """Feature: structure-inference-engine, Property 5: Equivalent reads agree

    **Validates: Requirements 4.7, 8.3**
    """
    for cand in _candidates(Engine().run(data)):
        first = {}
        for fr in cand.hypothesis.fields:
            assert first.setdefault(fr.name, fr.value[0]) == fr.value[0]
