"""Native point evidence and assignment API."""

from agrifusion_research.core.weak_labels.semantic.evidence.rules import evaluate_point_rules
from agrifusion_research.core.weak_labels.semantic.point.resolver import resolve_point_assignments

evaluate_point_evidence = evaluate_point_rules

__all__ = [
    "evaluate_point_evidence",
    "evaluate_point_rules",
    "resolve_point_assignments",
]
