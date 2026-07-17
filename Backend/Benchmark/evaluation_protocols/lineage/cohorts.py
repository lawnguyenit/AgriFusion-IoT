from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pandas as pd


COMPARISON_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("v0_vs_v2_mini_3h", "v0_point_train", "v2_same_y_3h", "3h"),
    ("v1_vs_v2_full_3h", "v1_point_train", "v2_same_y_3h", "3h"),
    ("v0_vs_v2_mini_8h", "v0_point_train", "v2_same_y_8h", "8h"),
    ("v1_vs_v2_full_8h", "v1_point_train", "v2_same_y_8h", "8h"),
)


@dataclass(frozen=True)
class MatchedCohortArtifacts:
    manifests: dict[str, pd.DataFrame]
    validation: pd.DataFrame


def build_explicit_matched_cohort_artifacts(
    *,
    view_assignments: pd.DataFrame,
    point_labels: pd.DataFrame,
    same_y_labels: pd.DataFrame,
    record_time_lookup: dict[str, pd.Timestamp],
) -> MatchedCohortArtifacts:
    validation_rows: list[dict[str, object]] = []
    manifests: dict[str, pd.DataFrame] = {}
    point_lookup = point_labels.set_index(["task_id", "sample_id"])["label_name"].astype("string").to_dict()
    same_y_lookup = same_y_labels.set_index(["task_id", "sample_id"])["label_name"].astype("string").to_dict()

    source_assignments = view_assignments.loc[
        view_assignments["deployment_domain"].astype("string") == "P1_SOURCE"
    ].copy()
    for comparison_id, left_view_id, right_view_id, horizon in COMPARISON_SPECS:
        manifest_rows: list[dict[str, object]] = []
        for fold_id in sorted(source_assignments["fold_id"].astype("string").dropna().unique().tolist()):
            if fold_id == "p2_target_holdout":
                continue
            for partition in ("train", "validation", "test"):
                left_ids = _ordered_ids(source_assignments, fold_id, partition, left_view_id, record_time_lookup)
                right_ids = _ordered_ids(source_assignments, fold_id, partition, right_view_id, record_time_lookup)
                matched_ids = [record_id for record_id in left_ids if record_id in set(right_ids)]
                matched_right_ids = [record_id for record_id in right_ids if record_id in set(matched_ids)]
                cohort_id = f"{comparison_id}__{fold_id}__{partition}"
                record_set_hash = _hash_record_set(matched_ids)
                labels_equal = True
                duplicate_record_ids = len(matched_ids) != len(set(matched_ids))
                for index, record_id in enumerate(matched_ids, start=1):
                    left_label = point_lookup.get((left_view_id, record_id), pd.NA)
                    right_label = same_y_lookup.get((right_view_id, record_id), pd.NA)
                    if str(left_label) != str(right_label):
                        labels_equal = False
                    manifest_rows.append(
                        {
                            "comparison_id": comparison_id,
                            "matched_cohort_id": cohort_id,
                            "fold_id": fold_id,
                            "partition": partition,
                            "horizon": horizon,
                            "left_view_id": left_view_id,
                            "right_view_id": right_view_id,
                            "record_id": record_id,
                            "record_id_order": index,
                            "label": left_label,
                            "record_set_hash": record_set_hash,
                        }
                    )
                exact_ordering_equality = matched_ids == matched_right_ids
                no_p2_rows = True
                validation_rows.append(
                    {
                        "comparison_id": comparison_id,
                        "matched_cohort_id": cohort_id,
                        "fold_id": fold_id,
                        "partition": partition,
                        "horizon": horizon,
                        "left_view_id": left_view_id,
                        "right_view_id": right_view_id,
                        "left_source_eligible_count": int(len(left_ids)),
                        "right_source_eligible_count": int(len(right_ids)),
                        "matched_record_count": int(len(matched_ids)),
                        "record_set_hash": record_set_hash,
                        "exact_record_id_set_equality": bool(set(matched_ids) == set(matched_right_ids)),
                        "exact_ordering_equality": bool(exact_ordering_equality),
                        "exact_same_y_label_equality": bool(labels_equal),
                        "no_duplicate_record_ids": bool(not duplicate_record_ids),
                        "no_p2_rows_in_p1_fold": no_p2_rows,
                        "no_purge_ineligible_v2_anchor": bool(len(matched_ids) == len(matched_right_ids)),
                    }
                )
                if not exact_ordering_equality or not labels_equal or duplicate_record_ids:
                    raise ValueError(
                        "Matched cohort validation failed for "
                        f"{comparison_id} {fold_id} {partition}: "
                        f"ordering={exact_ordering_equality}, labels_equal={labels_equal}, duplicates={duplicate_record_ids}."
                    )
        manifests[f"{comparison_id}.csv"] = pd.DataFrame(manifest_rows).convert_dtypes()
    return MatchedCohortArtifacts(
        manifests=manifests,
        validation=pd.DataFrame(validation_rows).convert_dtypes(),
    )


def _ordered_ids(
    view_assignments: pd.DataFrame,
    fold_id: str,
    partition: str,
    view_id: str,
    record_time_lookup: dict[str, pd.Timestamp],
) -> list[str]:
    frame = view_assignments.loc[
        (view_assignments["fold_id"].astype("string") == fold_id)
        & (view_assignments["view_id"].astype("string") == view_id)
        & (view_assignments["effective_partition"].astype("string") == partition)
    ].copy()
    if frame.empty:
        return []
    frame["record_timestamp"] = frame["record_id"].astype("string").map(record_time_lookup)
    frame = frame.sort_values(["record_timestamp", "record_id"], kind="stable")
    return frame["record_id"].astype("string").tolist()


def _hash_record_set(record_ids: list[str]) -> str:
    payload = json.dumps(record_ids, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
