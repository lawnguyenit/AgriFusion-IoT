from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DependencyArtifacts:
    registry: pd.DataFrame
    proxy_rich: pd.DataFrame
    proxy_reduced: pd.DataFrame
    validation: dict[str, object]


def build_dependency_artifacts() -> DependencyArtifacts:
    rows = [
        _row("point_low_moisture", "npk.soil_moisture_pct", "DIRECT_RULE_SOURCE", "v0|v1|v2|v6", "Primary direct rule source."),
        _row("point_low_moisture", "low_relative_moisture_flag", "DIRECT_RULE_SOURCE", "point|v2|v6", "Point predicate derived directly from current soil moisture."),
        _row("point_low_moisture", "low_run_length_ending_at_point", "DIRECT_RULE_SOURCE", "v2|v6", "Active low run state reused directly by persistent labels."),
        _row("point_low_moisture", "moisture_rise_delta", "DERIVED_RULE_PROXY", "point|v2", "Directly derived from the same moisture sequence."),
        _row("point_low_moisture", "ec_shift_delta_abs", "CORRELATED_SURROGATE", "point|v2", "Potentially correlated environmental surrogate, not a direct moisture rule source."),
        _row("point_low_moisture", "npk.soil_temp_c", "SAFE_CANDIDATE", "v0|v1", "Sensor channel not used directly by the low-moisture rule."),
        _row("point_low_moisture", "sht.temp_c", "SAFE_CANDIDATE", "v0|v1", "Ambient context channel."),
        _row("point_low_moisture", "sht.humidity_pct", "SAFE_CANDIDATE", "v0|v1", "Ambient context channel."),
        _row("point_low_moisture", "npk.ph", "SAFE_CANDIDATE", "v1", "Additional soil chemistry context."),
        _row("point_low_moisture", "npk.ec", "SAFE_CANDIDATE", "v0|v1", "Additional soil chemistry context."),
        _row("point_low_moisture", "npk.n_proxy", "SAFE_CANDIDATE", "v1", "Nutrient proxy context."),
        _row("point_low_moisture", "npk.p_proxy", "SAFE_CANDIDATE", "v1", "Nutrient proxy context."),
        _row("point_low_moisture", "npk.k_proxy", "SAFE_CANDIDATE", "v1", "Nutrient proxy context."),
        _row("point_low_moisture", "record.delta_prev_sec", "SPLIT_ONLY", "protocol", "Temporal completeness and cadence audit only."),
        _row("point_low_moisture", "record.gap_flag", "SPLIT_ONLY", "protocol", "Temporal completeness audit only."),
        _row("point_low_moisture", "record.missing_slot_count", "SPLIT_ONLY", "protocol", "Temporal completeness audit only."),
        _row("point_low_moisture", "npk.valid", "AUDIT_ONLY", "protocol", "Technical validity audit only."),
        _row("point_low_moisture", "sht.valid", "AUDIT_ONLY", "protocol", "Technical validity audit only."),
    ]
    registry = pd.DataFrame(rows).convert_dtypes()
    proxy_rich = registry.loc[
        registry["dependency_role"].astype("string").isin(
            ["DIRECT_RULE_SOURCE", "DERIVED_RULE_PROXY", "CORRELATED_SURROGATE", "SAFE_CANDIDATE"]
        )
    ].copy()
    proxy_reduced = registry.loc[registry["dependency_role"].astype("string") == "SAFE_CANDIDATE"].copy()
    contains_direct = bool((proxy_reduced["dependency_role"].astype("string") == "DIRECT_RULE_SOURCE").any())
    if contains_direct:
        raise ValueError("proxy_reduced_features.csv contains a DIRECT_RULE_SOURCE.")
    return DependencyArtifacts(
        registry=registry,
        proxy_rich=proxy_rich,
        proxy_reduced=proxy_reduced,
        validation={
            "proxy_reduced_contains_direct_rule_source": contains_direct,
            "proxy_reduced_validated": not contains_direct,
        },
    )


def _row(target_label: str, feature_name: str, dependency_role: str, feature_scope: str, notes: str) -> dict[str, object]:
    return {
        "target_label": target_label,
        "feature_name": feature_name,
        "dependency_role": dependency_role,
        "feature_scope": feature_scope,
        "notes": notes,
    }
