from __future__ import annotations

from pathlib import Path

import pandas as pd


LOW_POINT = "low_relative_moisture_point"
AUX_POINT = "unresolved_environmental_evidence_point"
REF_POINT = "reference_context_point"

LOW_TEMPORAL = "persistent_low_relative_moisture_at_anchor"
UNRES_TEMPORAL = "unresolved_environmental_evidence_at_anchor"
REF_TEMPORAL = "reference_context_at_anchor"


def load_temporal_target_frame(*, native_release_dir: Path, protocol_run_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load the current temporal-3h split and derive K1 additively.

    The native Q10-K3 release is never modified.  The protocol manifest owns
    the current sample universe, eligibility, and Fold 01 partitions.  K1 is
    derived only for rows that are already trainable under that temporal
    representation; exclusion reasons remain authoritative from the protocol.
    """

    native_release_dir = native_release_dir.resolve()
    protocol_run_dir = protocol_run_dir.resolve()
    temporal = pd.read_parquet(native_release_dir / "tasks" / "temporal" / "horizon_3h" / "assignments.parquet").convert_dtypes()
    resolutions = pd.read_parquet(native_release_dir / "audit" / "resolutions.parquet").convert_dtypes()
    protocol = pd.read_parquet(
        protocol_run_dir / "primary_protocol" / "runner" / "task_training_manifest.parquet"
    ).convert_dtypes()

    protocol = protocol.loc[
        protocol["feature_view_id"].astype("string").eq("v2_temporal_full_3h")
    ].copy()
    if protocol.empty:
        raise ValueError("The protocol manifest has no v2_temporal_full_3h rows.")
    if protocol["sample_id"].duplicated().any():
        raise ValueError("Temporal protocol rows must be unique by sample_id for this analysis lane.")

    temporal = temporal.loc[:, [
        "sample_id", "source_label", "label_name", "label_status", "train_inclusion_status"
    ]].copy()
    temporal["sample_id"] = temporal["sample_id"].astype("string")
    if temporal["sample_id"].duplicated().any():
        raise ValueError("Native temporal assignments must be unique by sample_id.")

    resolutions = resolutions.loc[
        resolutions["task_id"].astype("string").eq("TEMPORAL_ANCHOR")
        & resolutions["horizon_id"].astype("string").eq("3h"),
        ["sample_id", "support_depth_at_anchor", "required_k"],
    ].copy()
    resolutions["sample_id"] = resolutions["sample_id"].astype("string")
    if resolutions["sample_id"].duplicated().any():
        raise ValueError("Temporal resolutions must be unique by sample_id for horizon 3h.")

    frame = protocol.loc[:, [
        "sample_id", "fold_id", "partition", "final_trainability", "label_name",
        "label_status", "environment_id", "day_id", "segment_id", "source_canonical_hash",
        "protocol_artifact_hash",
    ]].rename(columns={"label_name": "protocol_label"}).copy()
    frame["sample_id"] = frame["sample_id"].astype("string")
    frame = frame.merge(temporal, on="sample_id", how="left", validate="one_to_one")
    frame = frame.merge(resolutions, on="sample_id", how="left", validate="one_to_one")
    if frame["source_label"].isna().any() or frame["support_depth_at_anchor"].isna().any():
        missing = frame.loc[
            frame["source_label"].isna() | frame["support_depth_at_anchor"].isna(), "sample_id"
        ].astype("string").head(5).tolist()
        raise ValueError(f"Native temporal evidence is missing for protocol rows: {missing}")

    frame["final_trainability"] = frame["final_trainability"].fillna(False).astype(bool)
    frame["support_depth_at_anchor"] = pd.to_numeric(
        frame["support_depth_at_anchor"], errors="coerce"
    ).fillna(0).astype(int)
    frame["source_label"] = frame["source_label"].astype("string")
    frame["protocol_label"] = frame["protocol_label"].astype("string")

    frame["derived_k3_label"] = frame.apply(
        lambda row: _derive_temporal_label(
            point_label=str(row["source_label"]),
            support_depth=int(row["support_depth_at_anchor"]),
            required_k=3,
        ),
        axis=1,
    ).astype("string")
    trainable = frame["final_trainability"]
    k3_mismatch = trainable & frame["derived_k3_label"].ne(frame["protocol_label"])
    if k3_mismatch.any():
        examples = frame.loc[k3_mismatch, ["sample_id", "source_label", "support_depth_at_anchor", "protocol_label", "derived_k3_label"]].head(5)
        raise ValueError("K3 derivation disagrees with the protocol on trainable rows:\n" + examples.to_string(index=False))

    frame["label_k3"] = frame["protocol_label"].where(
        ~trainable,
        frame["derived_k3_label"],
    ).astype("string")
    frame["label_k1"] = frame["protocol_label"].where(
        ~trainable,
        frame.apply(
            lambda row: _derive_temporal_label(
                point_label=str(row["source_label"]),
                support_depth=int(row["support_depth_at_anchor"]),
                required_k=1,
            ),
            axis=1,
        ),
    ).astype("string")

    metadata = {
        "protocol_feature_view_id": "v2_temporal_full_3h",
        "protocol_row_count": int(len(frame)),
        "trainable_row_count": int(trainable.sum()),
        "fold_ids": sorted(frame["fold_id"].astype("string").unique().tolist()),
        "native_required_k_values": sorted(resolutions["required_k"].dropna().astype(int).unique().tolist()),
        "k3_derivation_mismatch_count": int(k3_mismatch.sum()),
        "k1_low_count": int(frame.loc[trainable, "label_k1"].eq(LOW_TEMPORAL).sum()),
        "k3_low_count": int(frame.loc[trainable, "label_k3"].eq(LOW_TEMPORAL).sum()),
        "k1_unres_count": int(frame.loc[trainable, "label_k1"].eq(UNRES_TEMPORAL).sum()),
        "k3_unres_count": int(frame.loc[trainable, "label_k3"].eq(UNRES_TEMPORAL).sum()),
    }
    return frame.convert_dtypes(), metadata


def _derive_temporal_label(*, point_label: str, support_depth: int, required_k: int) -> str:
    if point_label == LOW_POINT:
        return LOW_TEMPORAL if support_depth >= required_k else UNRES_TEMPORAL
    if point_label == AUX_POINT:
        return UNRES_TEMPORAL
    if point_label == REF_POINT:
        return REF_TEMPORAL
    if point_label == "point_context_incomplete":
        return "point_context_incomplete_transfer"
    if point_label == "point_not_evaluable":
        return "point_not_evaluable"
    raise ValueError(f"Unhandled point label in K/window analysis: {point_label!r}")
