"""Native point evidence and assignment API."""

from Backend.Benchmark.weak_labels.semantic.evidence.rules import evaluate_point_rules
from Backend.Benchmark.weak_labels.semantic.point.resolver import resolve_point_assignments

evaluate_point_evidence = evaluate_point_rules

__all__ = [
    "evaluate_point_evidence",
    "evaluate_point_rules",
    "resolve_point_assignments",
]
