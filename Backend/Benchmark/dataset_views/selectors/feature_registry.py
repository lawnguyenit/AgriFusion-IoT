from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.Benchmark.dataset_views.contracts import FeatureCatalogEntry


def normalize_feature_catalog(catalog_df: pd.DataFrame) -> dict[str, FeatureCatalogEntry]:
    records: dict[str, FeatureCatalogEntry] = {}
    for row in catalog_df.to_dict(orient="records"):
        canonical_name = str(row.get("canonical_name", "")).strip()
        if not canonical_name:
            continue
        records[canonical_name] = FeatureCatalogEntry(
            canonical_name=canonical_name,
            feature_role=_normalize_text(row.get("feature_role")),
            used_by_label_rule=_normalize_bool(row.get("used_by_label_rule")),
            rule_proxy_level=_normalize_text(row.get("rule_proxy_level")),
            split_only=_normalize_bool(row.get("split_only")),
            allowed_views=_normalize_pipe_list(row.get("allowed_views")),
            forbidden_views=_normalize_pipe_list(row.get("forbidden_views")),
            eligible_for_model=_normalize_optional_bool(row.get("eligible_for_model")),
        )
    return records


def _normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _normalize_optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return _normalize_bool(value)


def _normalize_pipe_list(value: Any) -> tuple[str, ...]:
    if value is None or pd.isna(value):
        return ()
    parts = [part.strip() for part in str(value).split("|")]
    return tuple(part for part in parts if part)
