from __future__ import annotations

import pandas as pd


SUPPORT_PROFILE_ID = "SUPPORT_PROFILE_OBSERVED_MIN_7D_V1"
MIN_CLASS_COUNT = 20
MIN_EVENTS_PER_PARTITION = 5
MIN_EPISODE_CLUSTERS_PER_PARTITION = 5


def audit_candidate_support(
    *,
    labels: pd.DataFrame,
    registry: pd.DataFrame,
    splits: pd.DataFrame,
) -> pd.DataFrame:
    required_splits = {"sample_id", "partition", "fold_id", "timestamp_block_id"}
    if not required_splits.issubset(splits.columns):
        raise ValueError(f"Split artifact is missing required fields: {sorted(required_splits - set(splits.columns))}")
    if splits["sample_id"].astype("string").duplicated().any():
        raise ValueError("Split artifact must contain one row per sample_id.")
    if set(splits["partition"].astype("string")) - {"train", "validation", "test"}:
        raise ValueError("Support audit requires train/validation/test partitions only.")
    split_labels = splits.merge(labels, on="sample_id", how="left", validate="one_to_one")
    if split_labels["timestamp"].isna().any() or split_labels["entity_id"].isna().any():
        raise ValueError("Every split sample must resolve to a labeled timestamp and entity.")
    rows: list[dict[str, object]] = []
    for candidate in registry.to_dict(orient="records"):
        label_column = str(candidate["label_column"])
        if label_column not in split_labels:
            raise ValueError(f"Candidate label column is missing: {label_column}")
        candidate_frame = split_labels.loc[:, [
            "sample_id", "timestamp", "entity_id", "partition", "fold_id", label_column
        ]].copy()
        candidate_frame["_positive"] = (
            pd.to_numeric(candidate_frame[label_column], errors="coerce").eq(1).fillna(False).astype(bool)
        )
        candidate_frame = candidate_frame.sort_values(["entity_id", "timestamp", "sample_id"], kind="stable")
        prior_positive = candidate_frame.groupby("entity_id", sort=False)["_positive"].shift(fill_value=False)
        candidate_frame["_event_start"] = candidate_frame["_positive"] & ~prior_positive
        episode_number = candidate_frame.groupby("entity_id", sort=False)["_event_start"].cumsum()
        candidate_frame["_episode_id"] = (
            candidate_frame["entity_id"].astype("string") + ":" + episode_number.astype("string")
        )
        candidate_frame.loc[~candidate_frame["_positive"], "_episode_id"] = pd.NA
        for partition in ("train", "validation", "test"):
            part = candidate_frame.loc[candidate_frame["partition"].astype("string").eq(partition)]
            known = pd.to_numeric(part[label_column], errors="coerce").dropna()
            positives = int(known.eq(1).sum())
            negatives = int(known.eq(0).sum())
            unknown = int(len(part) - len(known))
            events = int(part["_event_start"].sum())
            clusters = int(part.loc[part["_positive"], "_episode_id"].nunique())
            class_floor = min(positives, negatives)
            passed = (
                class_floor >= MIN_CLASS_COUNT
                and events >= MIN_EVENTS_PER_PARTITION
                and clusters >= MIN_EPISODE_CLUSTERS_PER_PARTITION
            )
            rows.append({
                "support_profile_id": SUPPORT_PROFILE_ID,
                "support_mapping": "B2 TEMPORAL: class rows + persistent event onsets + distinct within-line persistent episodes",
                "target_id": candidate["target_id"],
                "q_id": candidate["q_id"],
                "threshold_scope": candidate.get("threshold_scope"),
                "tail_share": candidate["tail_share"],
                "tau_minutes": candidate["tau_minutes"],
                "label_column": label_column,
                "fold_id": str(part["fold_id"].iloc[0]) if not part.empty else pd.NA,
                "partition": partition,
                "row_count": int(len(part)),
                "known_label_count": int(len(known)),
                "unknown_label_count": unknown,
                "positive_class_count": positives,
                "negative_class_count": negatives,
                "minimum_class_count": class_floor,
                "persistent_event_count": events,
                "episode_cluster_count": clusters,
                "min_class_count_required": MIN_CLASS_COUNT,
                "min_event_count_required": MIN_EVENTS_PER_PARTITION,
                "min_episode_cluster_count_required": MIN_EPISODE_CLUSTERS_PER_PARTITION,
                "support_gate_pass": passed,
            })
    return pd.DataFrame(rows).convert_dtypes()


def summarize_entity_support(
    *, labels: pd.DataFrame, registry: pd.DataFrame, splits: pd.DataFrame
) -> pd.DataFrame:
    """Expose per-entity discrimination and evidence floors by partition."""
    entity_column = "entity_id" if "entity_id" in labels.columns else None
    rows: list[dict[str, object]] = []
    for candidate in registry.to_dict(orient="records"):
        label_column = str(candidate["label_column"])
        metadata = ["sample_id", *([entity_column] if entity_column else []), *(["timestamp"] if "timestamp" in labels.columns else [])]
        frame = splits.merge(labels.loc[:, [*metadata, label_column]], on="sample_id", how="left", validate="one_to_one")
        if entity_column is None:
            frame["_entity"] = "__all__"
            entity_key = "_entity"
        else:
            entity_key = entity_column
        order_columns = [entity_key, *(["timestamp"] if "timestamp" in frame.columns else []), "sample_id"]
        frame = frame.sort_values(order_columns, kind="stable").copy()
        numeric = pd.to_numeric(frame[label_column], errors="coerce")
        frame["_positive"] = numeric.eq(1).fillna(False).astype(bool)
        prior_positive = frame.groupby(entity_key, sort=False)["_positive"].shift(fill_value=False)
        frame["_event_start"] = frame["_positive"] & ~prior_positive
        episode_number = frame.groupby(entity_key, sort=False)["_event_start"].cumsum()
        frame["_episode_id"] = frame[entity_key].astype("string") + ":" + episode_number.astype("string")
        frame.loc[~frame["_positive"], "_episode_id"] = pd.NA
        for (entity, partition), part in frame.groupby([entity_key, "partition"], sort=True):
            values = pd.to_numeric(part[label_column], errors="coerce")
            known = values.dropna()
            positive = known.eq(1)
            negative = known.eq(0)
            positive_rows = part["_positive"]
            event_starts = part["_event_start"]
            episode_clusters = int(part.loc[positive_rows, "_episode_id"].nunique())
            discrimination_estimable = bool(positive.any() and negative.any())
            support_adequate = bool(
                int(positive.sum()) >= MIN_CLASS_COUNT
                and int(negative.sum()) >= MIN_CLASS_COUNT
                and int(event_starts.sum()) >= MIN_EVENTS_PER_PARTITION
                and episode_clusters >= MIN_EPISODE_CLUSTERS_PER_PARTITION
            )
            rows.append({
                "target_id": candidate.get("target_id"),
                "q_id": candidate.get("q_id"),
                "threshold_scope": candidate.get("threshold_scope"),
                "tail_share": candidate.get("tail_share"),
                "tau_minutes": candidate.get("tau_minutes"),
                "label_column": label_column,
                "entity_id": str(entity),
                "partition": str(partition),
                "row_count": int(len(part)),
                "known_label_count": int(len(known)),
                "known_label_fraction": float(len(known) / len(part)) if len(part) else 0.0,
                "unknown_label_count": int(len(part) - len(known)),
                "positive_count": int(positive.sum()),
                "negative_count": int(negative.sum()),
                "positive_prevalence_among_known": float(positive.mean()) if len(known) else pd.NA,
                "persistent_event_onsets": int(event_starts.sum()),
                "episode_cluster_count": episode_clusters,
                "within_entity_discrimination_estimable": discrimination_estimable,
                "within_entity_estimable": discrimination_estimable,
                "within_entity_support_adequate": support_adequate,
            })
    return pd.DataFrame(rows).convert_dtypes()


def summarize_entity_estimability(entity_support: pd.DataFrame) -> pd.DataFrame:
    """Separate two-class estimability from within-entity support adequacy."""
    if entity_support.empty:
        return pd.DataFrame(columns=[
            "target_id", "q_id", "threshold_scope", "tail_share", "tau_minutes",
            "partition", "entity_count", "estimable_entity_count",
            "support_adequate_entity_count", "non_estimable_entity_ids",
            "under_supported_entity_ids", "entity_discrimination_status",
            "entity_support_adequacy_status", "entity_claim_estimability_status",
        ])
    group_columns = [
        "target_id", "q_id", "threshold_scope", "tail_share", "tau_minutes", "partition",
    ]
    rows: list[dict[str, object]] = []
    for keys, part in entity_support.groupby(group_columns, dropna=False, sort=True):
        entities = part["entity_id"].astype("string")
        estimable = part["within_entity_discrimination_estimable"].fillna(False).astype(bool)
        adequate = part["within_entity_support_adequate"].fillna(False).astype(bool)
        count = int(estimable.sum())
        adequate_count = int(adequate.sum())
        total = int(len(part))
        if part["entity_id"].astype("string").eq("__all__").all():
            discrimination_status = "NOT_APPLICABLE"
            support_status = "NOT_APPLICABLE"
        else:
            discrimination_status = "PASS" if count == total else ("PARTIAL" if count else "FAIL")
            support_status = "PASS" if adequate_count == total else ("PARTIAL" if adequate_count else "FAIL")
        entity_ids = entities.tolist()
        rows.append({
            **dict(zip(group_columns, keys)),
            "entity_count": total,
            "estimable_entity_count": count,
            "support_adequate_entity_count": adequate_count,
            "non_estimable_entity_ids": "|".join(entities.loc[~estimable].tolist()),
            "under_supported_entity_ids": "|".join(entities.loc[~adequate].tolist()),
            "entity_discrimination_status": discrimination_status,
            "entity_support_adequacy_status": support_status,
            # Retain v1 field as a compatibility alias for mathematical two-class estimability.
            "entity_claim_estimability_status": discrimination_status,
            "interpretation_scope": (
                "single_series_no_entity_dimension"
                if discrimination_status == "NOT_APPLICABLE"
                else "discrimination_and_support_reported_separately; does_not_block_aggregate_model_fit"
            ),
        })
    return pd.DataFrame(rows).convert_dtypes()
