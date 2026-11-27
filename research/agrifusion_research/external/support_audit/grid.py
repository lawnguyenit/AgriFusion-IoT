from __future__ import annotations

import pandas as pd


def summarize_candidate_support_by_partition(
    *, labels: pd.DataFrame, registry: pd.DataFrame, splits: pd.DataFrame
) -> pd.DataFrame:
    """Summarize q/τ target support per split without imposing a gate."""
    required = {"sample_id", "partition", "fold_id"}
    if not required.issubset(splits.columns):
        raise ValueError(f"Split artifact is missing fields: {sorted(required - set(splits.columns))}")
    if splits["sample_id"].astype("string").duplicated().any():
        raise ValueError("Split artifact must contain one row per sample_id.")
    metadata = [column for column in ("timestamp", "entity_id") if column in labels.columns]
    frame = splits.merge(labels.loc[:, ["sample_id", *metadata]], on="sample_id", how="left", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for candidate in registry.to_dict(orient="records"):
        label_column = str(candidate["label_column"])
        if label_column not in labels.columns:
            raise ValueError(f"Candidate label column is missing: {label_column}")
        candidate_frame = splits.merge(
            labels.loc[:, ["sample_id", label_column, *metadata]],
            on="sample_id", how="left", validate="one_to_one",
        )
        group_key = "entity_id" if "entity_id" in candidate_frame else "fold_id"
        order = [group_key, "timestamp", "sample_id"] if "timestamp" in candidate_frame else [group_key, "sample_id"]
        candidate_frame = candidate_frame.sort_values(order, kind="stable")
        positive = pd.to_numeric(candidate_frame[label_column], errors="coerce").eq(1).fillna(False)
        prior_positive = positive.groupby(candidate_frame[group_key], sort=False).shift(fill_value=False)
        candidate_frame["_event_start"] = positive & ~prior_positive
        episode_number = candidate_frame.groupby(group_key, sort=False)["_event_start"].cumsum()
        candidate_frame["_episode_id"] = candidate_frame[group_key].astype("string") + ":" + episode_number.astype("string")
        candidate_frame.loc[~positive, "_episode_id"] = pd.NA
        for (fold_id, partition), part in candidate_frame.groupby(["fold_id", "partition"], sort=True):
            values = pd.to_numeric(part[label_column], errors="coerce")
            known = values.dropna()
            positives = int(known.eq(1).sum())
            negatives = int(known.eq(0).sum())
            rows.append({
                "target_id": candidate.get("target_id"),
                "q_id": candidate.get("q_id"),
                "threshold_scope": candidate.get("threshold_scope"),
                "tail_share": candidate.get("tail_share"),
                "threshold_quantile_level": candidate.get("threshold_quantile_level"),
                "tau_minutes": candidate.get("tau_minutes"),
                "persistence_basis": candidate.get("persistence_basis", "observation_count"),
                "label_column": label_column,
                "fold_id": str(fold_id),
                "partition": str(partition),
                "row_count": int(len(part)),
                "known_count": int(len(known)),
                "unknown_count": int(len(part) - len(known)),
                "positive_count": positives,
                "negative_count": negatives,
                "positive_prevalence_among_known": positives / len(known) if len(known) else pd.NA,
                "persistent_event_onsets": int(part["_event_start"].sum()),
                "positive_episode_clusters": int(part.loc[positive.loc[part.index], "_episode_id"].nunique()),
                "support_gate_applied": False,
            })
    return pd.DataFrame(rows).convert_dtypes()
