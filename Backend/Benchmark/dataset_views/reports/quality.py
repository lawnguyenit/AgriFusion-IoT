from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.Benchmark.dataset_views.contracts import FeatureCatalogEntry, ViewSelectionResult


def build_quality_report(
    view_id: str,
    feature_frame: pd.DataFrame,
    selection: ViewSelectionResult,
    catalog_index: dict[str, FeatureCatalogEntry],
    feature_metadata: dict[str, dict[str, Any]] | None = None,
    extra_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_summaries: list[dict[str, Any]] = []
    for feature_name in feature_frame.columns:
        series = feature_frame[feature_name]
        non_null = series.dropna()
        distinct_count = int(non_null.nunique(dropna=True))
        mode_fraction = 1.0
        if not non_null.empty:
            mode_fraction = float(non_null.value_counts(normalize=True, dropna=True).iloc[0])
        catalog_entry = catalog_index.get(feature_name)
        derived_metadata = (feature_metadata or {}).get(feature_name, {})
        feature_summaries.append(
            {
                "feature": feature_name,
                "dtype": str(series.dtype),
                "feature_role": (
                    catalog_entry.feature_role
                    if catalog_entry is not None
                    else derived_metadata.get("feature_role", "")
                ),
                "rule_proxy_level": (
                    catalog_entry.rule_proxy_level
                    if catalog_entry is not None
                    else derived_metadata.get("rule_proxy_level", "")
                ),
                "missing_count": int(series.isna().sum()),
                "missing_fraction": float(series.isna().mean()),
                "distinct_count": distinct_count,
                "is_constant": distinct_count <= 1,
                "is_near_constant": bool(mode_fraction >= 0.98),
                "top_value_fraction": mode_fraction,
                "derivation": derived_metadata.get("derivation", ""),
                "statistic": derived_metadata.get("statistic", ""),
                "window_hours": derived_metadata.get("window_hours"),
            }
        )

    proxy_removal_summary = {
        "removed_feature_count": int(len(selection.excluded_by_registry)),
        "removed_by_dependency_type": selection.dependency_type_counts,
        "removed_features": list(selection.excluded_by_registry),
    }

    report = {
        "view_id": view_id,
        "row_count": int(len(feature_frame)),
        "feature_count": int(feature_frame.shape[1]),
        "missingness": {feature: int(feature_frame[feature].isna().sum()) for feature in feature_frame.columns},
        "distinct_counts": {feature: int(feature_frame[feature].dropna().nunique()) for feature in feature_frame.columns},
        "constant_features": [summary["feature"] for summary in feature_summaries if summary["is_constant"]],
        "near_constant_features": [summary["feature"] for summary in feature_summaries if summary["is_near_constant"]],
        "feature_summaries": feature_summaries,
        "proxy_removal_summary": proxy_removal_summary,
        "unresolved_risk_summary": list(selection.unresolved_risks),
    }
    if extra_sections:
        report.update(extra_sections)
    return report
