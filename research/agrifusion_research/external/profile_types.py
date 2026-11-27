"""Dataclasses shared by the external dataset registry and the external lanes (no lane imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SourceFileSpec:
    name: str
    url: str


@dataclass(frozen=True)
class TargetSpec:
    target_id: str
    measurement_column: str
    tail_direction: str
    positive_label: str
    evidence_kind: str = "SENSOR_MEASUREMENT_WEAK_LABEL"
    input_feature_candidates: tuple[str, ...] = ()
    threshold_scopes: tuple[str, ...] = ("pooled",)


@dataclass(frozen=True)
class ExternalLabelProfile:
    dataset_id: str
    timestamp_column: str
    group_columns: tuple[str, ...]
    targets: tuple[TargetSpec, ...]
    scope_end_exclusive: str | None = None
    default_tau_minutes: tuple[int, ...] = ()
    tau_basis: str = "No domain-specific duration basis registered."
    tau_sources: tuple[str, ...] = ()
    persistence_basis: str = "observation_count"
    min_gap_cadence_fraction: float = 13 / 15
    max_gap_cadence_fraction: float = 17 / 15
    # Text written into the label policy manifest (moved from dataset_id branches in engine.py).
    threshold_fit_pooling: str = "one calibration ECDF per registered target"
    declared_review_anchor: Mapping[str, object] | None = field(default=None, compare=False)
    continuity_policy: str = "13/15 to 17/15 median cadence bounds"  # may use {g_max}


@dataclass(frozen=True)
class ExternalFeatureProfile:
    dataset_id: str
    timestamp_column: str
    group_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    context_columns: tuple[str, ...] = ()
    excluded_target_source_columns: tuple[str, ...] = ()
    scope_end_exclusive: str | None = None
    # How intake roles mark target-defining columns that X must exclude:
    #   "criterion_only_roles"        column_roles[name] == "criterion_only"
    #   "non_measurement_role_groups" every column of feature_and_criterion_roles except "measurements"
    excluded_columns_rule: str | None = None
    feature_policy_note: str | None = None
