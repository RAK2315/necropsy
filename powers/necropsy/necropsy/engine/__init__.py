"""Structure-inference engine public interface."""

from necropsy.engine.budget import Budget
from necropsy.engine.closure import check_closure, row_stride
from necropsy.engine.engine import Engine
from necropsy.engine.types import (
    AMBIGUITY_REASON,
    REASONS,
    TERMINATIONS,
    AmbiguousResult,
    Candidate,
    EngineResult,
    FailureReport,
    FieldRecord,
    Hypothesis,
    RejectionEntry,
    VerifiedHypothesis,
    hypothesis_key,
)

__all__ = [
    "Engine", "Budget", "check_closure", "row_stride",
    "FieldRecord", "Hypothesis", "hypothesis_key", "RejectionEntry", "Candidate",
    "VerifiedHypothesis", "AmbiguousResult", "FailureReport", "EngineResult",
    "REASONS", "TERMINATIONS", "AMBIGUITY_REASON",
]
