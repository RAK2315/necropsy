"""Engine: probe phase and candidate assembly. Revision and generic phases are hooks."""

from __future__ import annotations

import time
from typing import Callable

from necropsy.engine.budget import Budget
from necropsy.engine.closure import ClosureVerdict, check_closure, row_stride
from necropsy.engine.coherence import coherence_gap, row_coherence
from necropsy.engine.probes import PROBES
from necropsy.engine.types import (
    AMBIGUITY_REASON,
    AmbiguousResult,
    Candidate,
    EngineResult,
    FailureReport,
    Hypothesis,
    RejectionEntry,
    VerifiedHypothesis,
)

MIN_INPUT_BYTES = 3


class Engine:
    def __init__(self, deadline_seconds: float = 5.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._deadline_seconds = deadline_seconds
        self._clock = clock

    def run(self, data: bytes) -> EngineResult:
        data = bytes(data)
        if len(data) < MIN_INPUT_BYTES:
            return FailureReport(
                "input_too_short",
                (RejectionEntry("input_too_short", "engine",
                                detail=f"{len(data)} bytes; at least {MIN_INPUT_BYTES} required"),),
                0, len(data),
            )
        budget = Budget(self._deadline_seconds, clock=self._clock)
        rejections: list[RejectionEntry] = []
        return self._run(data, budget, rejections)

    def _run(self, data: bytes, budget: Budget, rejections: list[RejectionEntry]) -> EngineResult:
        winners: list[tuple[Hypothesis, ClosureVerdict]] = []
        seeds: list[Hypothesis] = []
        for name, probe in PROBES:
            stop = budget.stop_reason()
            if stop:
                return self._failure(stop, data, budget, rejections, winners)
            outcome = probe(data)
            if outcome is None:
                continue
            rejections.extend(outcome.rejections)
            seeds.append(outcome.seed)
            stop = budget.charge()
            if stop:
                return self._failure(stop, data, budget, rejections, winners)
            verdict = check_closure(outcome.seed, data)
            if verdict.ok:
                winners.append((outcome.seed, verdict))
            else:
                rejections.append(RejectionEntry(
                    verdict.reason, name, outcome.seed, verdict.discrepancy))

        if winners:
            candidates: list[Candidate] = []
            for h, v in winners:
                cand = self._candidate(h, v, budget)
                if isinstance(cand, str):
                    return self._failure(cand, data, budget, rejections, winners)
                candidates.append(cand)
            return self._outcome(candidates, "probe", data, budget, rejections)

        if seeds:
            # HOOK (task 7.2): revision phase over `seeds` goes here.
            return FailureReport("exhausted", tuple(rejections), budget.checks, len(data))
        # HOOK (task 7.3): generic dispatch goes here (no probe matched).
        return FailureReport("exhausted", tuple(rejections), budget.checks, len(data))

    def _candidate(self, h: Hypothesis, verdict: ClosureVerdict, budget: Budget,
                   alternative_paths: tuple[tuple[str, ...], ...] = ()) -> Candidate | str:
        """Build a Candidate, or return the stop reason if the budget is spent."""
        stop = budget.stop_reason()
        if stop:
            return stop
        stride = row_stride(h.width, h.bit_depth, h.row_alignment)
        score, status = row_coherence(verdict.decoded, h.height, stride)
        return self._build(h, verdict, stride, score, status, alternative_paths)

    @staticmethod
    def _build(h, verdict, stride, score, status, alternative_paths=()) -> Candidate:
        return Candidate(
            hypothesis=h,
            row_stride=stride,
            expected_decoded_bytes=stride * h.height,
            data_start=verdict.data_start,
            data_end=verdict.data_end,
            trailer=verdict.trailer,
            coherence_score=score,
            coherence_status=status,
            alternative_paths=tuple(alternative_paths),
            decoded=verdict.decoded,
        )

    def _outcome(self, candidates: list[Candidate], stage: str, data: bytes,
                 budget: Budget, rejections: list[RejectionEntry]) -> EngineResult:
        """One winner is RESOLVED; several are AMBIGUOUS in discovery order. Never ranks."""
        if len(candidates) == 1:
            return VerifiedHypothesis(candidates[0], stage, tuple(rejections),
                                      budget.checks, len(data))
        return AmbiguousResult(
            tuple(candidates), stage, AMBIGUITY_REASON.format(n=len(candidates)),
            coherence_gap(c.coherence_score for c in candidates),
            tuple(rejections), budget.checks, len(data),
        )

    def _failure(self, stop: str, data: bytes, budget: Budget,
                 rejections: list[RejectionEntry],
                 winners: list[tuple[Hypothesis, ClosureVerdict]]) -> FailureReport:
        partial = tuple(
            self._build(h, v, row_stride(h.width, h.bit_depth, h.row_alignment),
                        None, "not_computed")
            for h, v in winners
        )
        return FailureReport(stop, tuple(rejections), budget.checks, len(data), partial)
