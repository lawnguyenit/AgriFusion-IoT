"""Rule-firing and evidence evaluation facade."""

from Backend.Benchmark.weak_labels.semantic.evidence.rules import RULES, evaluate_point_rules

__all__ = ["RULES", "evaluate_point_rules"]
