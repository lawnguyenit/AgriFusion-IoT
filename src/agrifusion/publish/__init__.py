"""Publish canonical Layer1 output to the dashboard contract (`result/*`). See README.md."""
from .mapping import build_groups, load_schema, validate_result
from .planner import PublishPlan, build_plan

__all__ = ["PublishPlan", "build_groups", "build_plan", "load_schema", "validate_result"]
