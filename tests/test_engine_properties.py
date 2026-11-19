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


# ---------------------------------------------------------------- Properties 7, 9, 10, 15
import itertools
from unittest.mock import patch

from necropsy.engine.types import REASONS, TERMINATIONS, hypothesis_key
import necropsy.engine.engine as engine_module
import necropsy.engine.generic as generic_module

REVISION_CORPUS = ("mystery_b", "mystery_h", "mystery_i")


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_outcome_well_formed(data):
    """Feature: structure-inference-engine, Property 7: Outcome well-formed

    **Validates: Requirements 5.6, 5.7, 10.1, 10.2, 10.3**
    """
    result = Engine().run(data)
    assert isinstance(result, RESULT_TYPES)
    if isinstance(result, VerifiedHypothesis):
        assert result.status == "RESOLVED"
    elif isinstance(result, AmbiguousResult):
        assert result.status == "UNRESOLVED_AMBIGUITY"
        assert len(result.candidates) >= 2
        keys = [hypothesis_key(c.hypothesis) for c in result.candidates]
        assert len(set(keys)) == len(keys)
    else:
        assert result.status == "FAILED"
        assert result.termination in TERMINATIONS
    for rej in result.rejections:
        assert rej.reason in REASONS


def _keys(result):
    return [hypothesis_key(c.hypothesis) for c in _candidates(result)]


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_no_duplicate_hypotheses(data):
    """Feature: structure-inference-engine, Property 9: No duplicate hypotheses

    **Validates: Requirements 3.3**
    """
    seen = []

    def spy(h, d, *args, **kwargs):
        seen.append(hypothesis_key(h))
        return check_closure(h, d, *args, **kwargs)

    with patch.object(engine_module, "check_closure", spy), \
            patch.object(generic_module, "check_closure", spy):
        result = Engine().run(data)
    keys = _keys(result)
    assert len(set(keys)) == len(keys)
    assert len(set(seen)) == len(seen)


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_deterministic(data):
    """Feature: structure-inference-engine, Property 10: Deterministic

    **Validates: Requirements 3.6**
    """
    assert Engine(deadline_seconds=3600.0).run(data) == Engine(deadline_seconds=3600.0).run(data)


def _path_sets(result):
    return [
        {c.hypothesis.revision_path} | set(c.alternative_paths)
        for c in _candidates(result)
    ]


def _check_permutations(data):
    base = Engine().run(data)
    if getattr(base, "stage", None) != "revision":
        return
    for perm in itertools.permutations(engine_module.STRATEGIES):
        with patch.object(engine_module, "STRATEGIES", perm):
            other = Engine().run(data)
        assert type(other) is type(base)
        assert other.status == base.status
        assert _keys(other) == _keys(base)
        assert _path_sets(other) == _path_sets(base)


@_with_corpus_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs)
def test_alternative_paths_well_formed(data):
    """Feature: structure-inference-engine, Property 15: Alternative paths are well-formed

    **Validates: Requirements 3.6, 3.9, 3.10**
    """
    result = Engine().run(data)
    stage = getattr(result, "stage", None)
    for cand in _candidates(result):
        path = cand.hypothesis.revision_path
        alts = cand.alternative_paths
        if stage in ("probe", "generic"):
            assert alts == ()
        assert len(set(alts)) == len(alts)
        for alt in alts:
            assert len(alt) == len(path)
            assert alt != path
    _check_permutations(data)


def test_strategy_permutations_on_revision_corpus():
    """Feature: structure-inference-engine, Property 15: Alternative paths are well-formed

    **Validates: Requirements 3.6, 3.9, 3.10**
    """
    for name in REVISION_CORPUS:
        data = corpus_bytes(name)
        assert Engine().run(data).stage == "revision", name
        _check_permutations(data)


# ---------------------------------------------------------------- Property 8
from hypothesis import strategies as st

_SPECIAL_SCORES = (0.0, 5e-324, 1e-300, 1.0, 1e300, 1.7976931348623157e308)


def _outcome(result):
    return result.status, _keys(result)


import random as _random


def _with_corpus_and_random_examples(test):
    for i, name in enumerate(CORPUS_NAMES):
        test = example(corpus_bytes(name), _random.Random(i))(test)
    return test


@_with_corpus_and_random_examples
@settings(max_examples=100, deadline=None)
@given(engine_inputs, st.randoms(use_true_random=False))
def test_coherence_cannot_change_outcome(data, rnd):
    """Feature: structure-inference-engine, Property 8: Coherence cannot change the outcome

    **Validates: Requirements 10.5, 11.1, 11.8**
    """
    baseline = _outcome(Engine().run(data))

    def random_score(*args, **kwargs):
        if rnd.random() < 0.5:
            score = rnd.choice(_SPECIAL_SCORES)
        else:
            score = rnd.uniform(0.0, 1e300) * rnd.choice((1e-300, 1e-10, 1.0, 1e5))
        return score, "scored"

    with patch.object(engine_module, "row_coherence", random_score):
        assert _outcome(Engine().run(data)) == baseline

    with patch.object(engine_module, "row_coherence",
                      lambda *a, **k: (None, "unscorable")):
        assert _outcome(Engine().run(data)) == baseline
