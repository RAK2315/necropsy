"""Engine-level property tests: Properties 1 and 2."""
import time

from hypothesis import example, given, settings

from necropsy.engine import (
    AmbiguousResult, Engine, FailureReport, VerifiedHypothesis,
)
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
