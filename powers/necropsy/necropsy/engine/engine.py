"""Engine: probe, revision and generic phases, and candidate assembly."""

from __future__ import annotations

import time
from typing import Callable

from necropsy.engine.budget import Budget
from necropsy.engine.closure import ClosureVerdict, check_closure, row_stride
from necropsy.engine.coherence import coherence_gap, row_coherence
from necropsy.engine.generic import generic_search
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
    hypothesis_key,
)
from necropsy.engine.strategies import STRATEGIES

MIN_INPUT_BYTES = 3
REVISION_DEPTHS = (1, 2, 3)


class Engine:
    def __init__(self, deadline_seconds: float = 5.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._deadline_seconds = deadline_seconds
        self._clock = clock

    def run(self, data: bytes) -> EngineResult:
        """Never raises. The wrapper is a last line of defence; inner code does not rely on it."""
        try:
            return self._run_checked(data)
        except Exception as exc:
            size = len(data) if isinstance(data, (bytes, bytearray)) else 0
            return FailureReport(
                "internal_error",
                (RejectionEntry("internal_error", "engine",
                                detail=f"{type(exc).__name__}: {exc}"),),
                0, size,
            )

    def _run_checked(self, data: bytes) -> EngineResult:
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
            if outcome.seed is None:  # Requirement 2.10: declined; no seed, no check
                continue
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
                    return self._failure(cand, data, budget, rejections, winners, candidates)
                candidates.append(cand)
            return self._outcome(candidates, "probe", data, budget, rejections)

        if seeds:
            return self._revise(seeds, data, budget, rejections)
        return self._generic(data, budget, rejections)

    def _generic(self, data: bytes, budget: Budget,
                 rejections: list[RejectionEntry]) -> EngineResult:
        """Generic Search; runs only when no probe matched."""
        def on_reject(h: Hypothesis, v: ClosureVerdict) -> None:
            rejections.append(RejectionEntry(v.reason, "generic", h, v.discrepancy))

        outcome = generic_search(data, budget, on_reject)
        found = list(outcome.found)
        if outcome.stop:
            return self._failure(outcome.stop, data, budget, rejections, found)
        candidates: list[Candidate] = []
        for h, v in found:
            cand = self._candidate(h, v, budget)
            if isinstance(cand, str):
                return self._failure(cand, data, budget, rejections, found, candidates)
            candidates.append(cand)
        if not candidates:
            return self._exhausted(data, budget, rejections)
        return self._outcome(candidates, "generic", data, budget, rejections)

    def _revise(self, seeds: list[Hypothesis], data: bytes, budget: Budget,
                rejections: list[RejectionEntry]) -> EngineResult:
        """Breadth-first revision to depth 3. Stops at the first closing depth."""
        seen: dict[tuple, int] = {hypothesis_key(s): 0 for s in seeds}
        alternatives: dict[tuple, list[tuple[str, ...]]] = {}
        frontier = list(seeds)
        for depth in REVISION_DEPTHS:
            winners: list[tuple[Hypothesis, ClosureVerdict]] = []
            next_frontier: list[Hypothesis] = []
            for h in frontier:
                for _name, fn in STRATEGIES:
                    for c in fn(h):
                        k = hypothesis_key(c)
                        if k in seen:
                            if seen[k] == depth:
                                alternatives.setdefault(k, []).append(c.revision_path)
                            continue
                        seen[k] = depth
                        stop = budget.charge()
                        if stop:
                            return self._failure(stop, data, budget, rejections, winners)
                        v = check_closure(c, data)
                        if v.ok:
                            winners.append((c, v))
                        else:
                            rejections.append(RejectionEntry(
                                v.reason, "revision:" + "->".join(c.revision_path),
                                c, v.discrepancy))
                            next_frontier.append(c)
            if winners:
                candidates: list[Candidate] = []
                for c, v in winners:
                    cand = self._candidate(
                        c, v, budget, tuple(alternatives.get(hypothesis_key(c), ())))
                    if isinstance(cand, str):
                        return self._failure(cand, data, budget, rejections, winners, candidates)
                    candidates.append(cand)
                return self._outcome(candidates, "revision", data, budget, rejections)
            frontier = next_frontier
        return self._exhausted(data, budget, rejections)

    @staticmethod
    def _exhausted(data: bytes, budget: Budget,
                   rejections: list[RejectionEntry]) -> FailureReport:
        """Requirement 5.12: `exhausted` needs at least one closure check; otherwise
        `no_hypothesis_checked`."""
        termination = "no_hypothesis_checked" if budget.checks == 0 else "exhausted"
        return FailureReport(termination, tuple(rejections), budget.checks, len(data))

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
                 winners: list[tuple[Hypothesis, ClosureVerdict]],
                 computed: list[Candidate] = ()) -> FailureReport:
        # `computed` is the prefix of winners whose coherence step already ran;
        # those keep their score and status. The rest were never scored.
        partial = tuple(computed) + tuple(
            self._build(h, v, row_stride(h.width, h.bit_depth, h.row_alignment),
                        None, "not_computed")
            for h, v in winners[len(computed):]
        )
        return FailureReport(stop, tuple(rejections), budget.checks, len(data), partial)
