"""First-class assignment and resolution exports."""

from Backend.Benchmark.weak_labels.semantic.point.resolver import resolve_point_assignments
from Backend.Benchmark.weak_labels.semantic.temporal.resolver import resolve_temporal_assignments

__all__ = ["resolve_point_assignments", "resolve_temporal_assignments"]
