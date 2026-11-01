"""Explicit boundaries between full-reference audit and evaluator inputs."""
from dataclasses import dataclass
import numpy as np

MODELS = ("COMPLETE_HGB", "SOFT_EM_HGB", "MARKOV", "CONSTANT",
          "LOGISTIC_COMPLETE_H6", "HGB_COMPLETE_H24")
PARTITIONS = ("train", "development", "selection", "assessment")
HOUR_NS = 3_600_000_000_000


class FailedSupport(ValueError):
    """A declared source/fit cannot support the requested experiment."""


@dataclass(frozen=True)
class Segment:
    segment_id: str
    entity: str
    partition: str
    keys: np.ndarray
    values: np.ndarray
    states: np.ndarray
    score: np.ndarray


@dataclass(frozen=True)
class EvaluationSegment:
    """No truth, numeric hidden values, or corruption positions in this API."""
    segment_id: str
    keys: np.ndarray
    observed: np.ndarray
    score: np.ndarray
    probabilities: np.ndarray  # [model, time], fixed during reference sensitivity

    def validate(self, n_models: int = len(MODELS)) -> None:
        n = len(self.observed)
        if self.probabilities.shape != (n_models, n):
            raise ValueError("Probability/cohort shape mismatch")
        if len(self.keys) != n or self.score.shape != (n,):
            raise ValueError("Scored keys/mask mismatch")
        if self.score.dtype != np.dtype(bool) or len(np.unique(self.keys)) != n:
            raise ValueError("Scored mask must be Boolean and origin keys unique")
        if not np.isin(self.observed, [-1, 0, 1]).all():
            raise ValueError("Observed states must be -1/0/1")
        p = self.probabilities
        if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
            raise ValueError("Probabilities must be finite in [0,1]")


def verdict(lower: float, upper: float, tolerance: float = 1e-12) -> str:
    if lower > upper + tolerance:
        raise ValueError("Invalid comparison interval")
    if upper < -tolerance:
        return "A_BETTER"
    if lower > tolerance:
        return "B_BETTER"
    return "INCONCLUSIVE"


def comparison_reason(lower, upper, tolerance=1e-12):
    if verdict(lower, upper, tolerance) != "INCONCLUSIVE":
        return "certified_strict_order"
    if max(abs(lower), abs(upper)) <= tolerance:
        return "no_strict_difference_within_tolerance"
    return "inconclusive_reference_set"
