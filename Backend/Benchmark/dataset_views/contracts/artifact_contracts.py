from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import GLOBAL_FORBIDDEN_MODEL_FIELDS
from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, stable_hash_object


DEFAULT_IDENTIFIER_COLUMNS: tuple[str, ...] = ("record.id", "source_row_position")


def build_feature_columns_payload(
    *,
    view_id: str,
    ordered_feature_list: list[str],
    metadata_columns: list[str],
    audit_only_columns: list[str],
    identifier_source_path: Path,
    source_manifest_payload: dict[str, object],
) -> dict[str, object]:
    payload = {
        "view_id": view_id,
        "allowed_feature_columns": list(ordered_feature_list),
        "allowed_feature_columns_hash": stable_hash_object(list(ordered_feature_list)),
        "identifier_columns": list(DEFAULT_IDENTIFIER_COLUMNS),
        "identifier_source_path": str(identifier_source_path.resolve()),
        "identifier_source_hash": str(
            source_manifest_payload.get("shared_artifacts", {})
            .get("row_index", {})
            .get("file_hash", "UNKNOWN")
        ),
        "audit_only_columns": sorted(set(metadata_columns).union(audit_only_columns)),
        "forbidden_columns": list(GLOBAL_FORBIDDEN_MODEL_FIELDS),
        "source_canonical_hash": str(source_manifest_payload["source"]["canonical_history_hash"]),
        "materialization_config_hash": str(source_manifest_payload["source"]["materialization_config_hash"]),
        "feature_generator_code_commit": str(source_manifest_payload["source"]["pipeline_code_commit"]),
    }
    payload["payload_hash"] = stable_hash_object(payload)
    return payload


def build_schema_payload(*, view_id: str, feature_frame: pd.DataFrame) -> dict[str, object]:
    columns = [{"name": column, "dtype": str(dtype)} for column, dtype in feature_frame.dtypes.items()]
    return {
        "view_id": view_id,
        "row_count": int(len(feature_frame)),
        "feature_count": int(feature_frame.shape[1]),
        "columns": columns,
        "schema_hash": dataframe_schema_hash(feature_frame),
    }
