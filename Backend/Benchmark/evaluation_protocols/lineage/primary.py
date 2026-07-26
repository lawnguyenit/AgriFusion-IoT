from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.scope import PRIMARY_COMPARISON_IDS, PRIMARY_FEATURE_VIEW_IDS, PRIMARY_FOLD_IDS


PRIMARY_PROTOCOL_ID = "P1_SOURCE_PRIMARY_5DAY_FOLD_01_03"
PRIMARY_PROTOCOL_VERSION = "2026-07-16.eval-protocol.v2"
PRIMARY_BLOCK_DAYS = 5
PRIMARY_PARTITIONS: tuple[str, ...] = ("train", "validation", "test")


@dataclass(frozen=True)
class PrimaryProtocolArtifacts:
    fold_manifest: pd.DataFrame
    base_split_assignments: pd.DataFrame
    view_split_assignments: pd.DataFrame
    matched_cohort_manifests: dict[str, pd.DataFrame]
    matched_cohort_validation: pd.DataFrame
    runner_contract: dict[str, object]
    validation: pd.DataFrame


def build_primary_protocol_artifacts(
    *,
    five_day_fold_manifest: pd.DataFrame,
    base_split_assignments: pd.DataFrame,
    view_split_assignments: pd.DataFrame,
    matched_cohort_manifests: dict[str, pd.DataFrame],
    matched_cohort_validation: pd.DataFrame,
) -> PrimaryProtocolArtifacts:
    fold_manifest = _select_primary_folds(five_day_fold_manifest)
    filtered_base = base_split_assignments.loc[
        base_split_assignments["fold_id"].astype("string").isin(set(PRIMARY_FOLD_IDS) | {"p2_target_holdout"})
    ].copy()
    filtered_view = view_split_assignments.loc[
        view_split_assignments["fold_id"].astype("string").isin(set(PRIMARY_FOLD_IDS) | {"p2_target_holdout"})
    ].copy()
    filtered_validation = matched_cohort_validation.loc[
        matched_cohort_validation["fold_id"].astype("string").isin(PRIMARY_FOLD_IDS)
        & matched_cohort_validation["partition"].astype("string").isin(PRIMARY_PARTITIONS)
    ].copy()
    filtered_manifests = {
        name: frame.loc[
            frame["fold_id"].astype("string").isin(PRIMARY_FOLD_IDS)
            & frame["partition"].astype("string").isin(PRIMARY_PARTITIONS)
        ].copy()
        for name, frame in matched_cohort_manifests.items()
    }
    validation_rows = _build_primary_validation_rows(
        fold_manifest=fold_manifest,
        matched_cohort_validation=filtered_validation,
        matched_cohort_manifests=filtered_manifests,
    )
    runner_contract = _build_runner_contract(filtered_validation)
    _assert_runner_contract(filtered_manifests, filtered_validation, runner_contract)
    return PrimaryProtocolArtifacts(
        fold_manifest=fold_manifest.convert_dtypes(),
        base_split_assignments=filtered_base.convert_dtypes(),
        view_split_assignments=filtered_view.convert_dtypes(),
        matched_cohort_manifests={name: frame.convert_dtypes() for name, frame in filtered_manifests.items()},
        matched_cohort_validation=filtered_validation.convert_dtypes(),
        runner_contract=runner_contract,
        validation=pd.DataFrame(validation_rows).convert_dtypes(),
    )


def _select_primary_folds(five_day_fold_manifest: pd.DataFrame) -> pd.DataFrame:
    selected = five_day_fold_manifest.loc[
        five_day_fold_manifest["fold_id"].astype("string").isin(PRIMARY_FOLD_IDS)
        & five_day_fold_manifest["partition"].astype("string").isin(PRIMARY_PARTITIONS)
    ].copy()
    expected_rows = len(PRIMARY_FOLD_IDS) * len(PRIMARY_PARTITIONS)
    if len(selected) != expected_rows:
        raise ValueError(
            f"Primary protocol requires {expected_rows} rows for 5-day folds {PRIMARY_FOLD_IDS}, found {len(selected)}."
        )
    ineligible = selected.loc[~selected["primary_benchmark_eligible"].astype(bool)].copy()
    if not ineligible.empty:
        raise ValueError(
            "Primary 5-day fold lock failed because some partitions are not primary-benchmark eligible: "
            f"{ineligible.loc[:, ['fold_id', 'partition', 'failed_criteria']].to_dict(orient='records')}"
        )
    selected["protocol_id"] = PRIMARY_PROTOCOL_ID
    selected["protocol_version"] = PRIMARY_PROTOCOL_VERSION
    selected["protocol_role"] = "primary"
    return selected.sort_values(["fold_id", "partition"], kind="stable").reset_index(drop=True)


def _build_primary_validation_rows(
    *,
    fold_manifest: pd.DataFrame,
    matched_cohort_validation: pd.DataFrame,
    matched_cohort_manifests: dict[str, pd.DataFrame],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in fold_manifest.to_dict(orient="records"):
        rows.append(
            {
                "scope": "primary_fold_partition",
                "entity_id": f"{row['fold_id']}::{row['partition']}",
                "check_name": "primary_benchmark_eligible",
                "passed": bool(row["primary_benchmark_eligible"]),
                "details": row["status_reason"],
            }
        )
    for row in matched_cohort_validation.to_dict(orient="records"):
        cohort_id = str(row["matched_cohort_id"])
        manifest_name = f"{str(row['comparison_id'])}.csv"
        manifest = matched_cohort_manifests.get(manifest_name, pd.DataFrame())
        manifest_rows = manifest.loc[manifest["matched_cohort_id"].astype("string") == cohort_id].copy()
        rows.append(
            {
                "scope": "matched_cohort",
                "entity_id": cohort_id,
                "check_name": "runner_gate_ready",
                "passed": bool(
                    row["exact_record_id_set_equality"]
                    and row["exact_ordering_equality"]
                    and row["exact_same_y_label_equality"]
                    and row["no_duplicate_record_ids"]
                    and row["no_p2_rows_in_p1_fold"]
                    and row["no_purge_ineligible_v2_anchor"]
                    and int(row["matched_record_count"]) > 0
                    and not manifest_rows.empty
                ),
                "details": json.dumps(
                    {
                        "comparison_id": row["comparison_id"],
                        "fold_id": row["fold_id"],
                        "partition": row["partition"],
                        "matched_record_count": int(row["matched_record_count"]),
                        "record_set_hash": str(row["record_set_hash"]),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )
    return rows


def _build_runner_contract(matched_cohort_validation: pd.DataFrame) -> dict[str, object]:
    required_rows = matched_cohort_validation.sort_values(
        ["comparison_id", "fold_id", "partition"],
        kind="stable",
    )
    required_ids = required_rows["matched_cohort_id"].astype("string").tolist()
    cohort_hashes = {
        str(row["matched_cohort_id"]): str(row["record_set_hash"])
        for row in required_rows.to_dict(orient="records")
    }
    contract = {
        "protocol_id": PRIMARY_PROTOCOL_ID,
        "protocol_version": PRIMARY_PROTOCOL_VERSION,
        "primary_block_days": PRIMARY_BLOCK_DAYS,
        "primary_fold_ids": list(PRIMARY_FOLD_IDS),
        "primary_partitions": list(PRIMARY_PARTITIONS),
        "primary_feature_views": list(PRIMARY_FEATURE_VIEW_IDS),
        "target_holdout_fold_id": "p2_target_holdout",
        "required_comparisons": list(PRIMARY_COMPARISON_IDS),
        "required_matched_cohort_ids": required_ids,
        "matched_cohort_hashes": cohort_hashes,
        "frozen_target_evaluation": {
            "training_aggregation": "single_refit_not_fold_pooling",
            "source_training_scope": "union_unique_p1_rows_across_primary_folds",
            "target_scope": "all_eligible_p2_target_test_rows",
            "target_manifest_filename": "frozen_target_manifest.parquet",
        },
        "assertions": [
            "exact_record_id_set_equality",
            "exact_ordering_equality",
            "exact_same_y_label_equality",
            "no_duplicate_record_ids",
            "no_p2_rows_in_p1_fold",
            "no_purge_ineligible_v2_anchor",
            "matched_record_count_gt_zero",
        ],
    }
    contract["contract_hash"] = hashlib.sha256(
        json.dumps(contract, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return contract


def _assert_runner_contract(
    matched_cohort_manifests: dict[str, pd.DataFrame],
    matched_cohort_validation: pd.DataFrame,
    runner_contract: dict[str, object],
) -> None:
    for cohort_id in runner_contract["required_matched_cohort_ids"]:
        rows = matched_cohort_validation.loc[
            matched_cohort_validation["matched_cohort_id"].astype("string") == str(cohort_id)
        ].copy()
        if len(rows) != 1:
            raise ValueError(f"Runner contract cohort {cohort_id} expected exactly one validation row, found {len(rows)}.")
        row = rows.iloc[0]
        if not bool(
            row["exact_record_id_set_equality"]
            and row["exact_ordering_equality"]
            and row["exact_same_y_label_equality"]
            and row["no_duplicate_record_ids"]
            and row["no_p2_rows_in_p1_fold"]
            and row["no_purge_ineligible_v2_anchor"]
            and int(row["matched_record_count"]) > 0
        ):
            raise ValueError(
                "Runner contract cohort gate failed for "
                f"{cohort_id}: {rows.to_dict(orient='records')}"
            )
        manifest_name = f"{str(row['comparison_id'])}.csv"
        manifest = matched_cohort_manifests.get(manifest_name)
        if manifest is None:
            raise ValueError(f"Runner contract missing manifest {manifest_name} for cohort {cohort_id}.")
        manifest_rows = manifest.loc[manifest["matched_cohort_id"].astype("string") == str(cohort_id)].copy()
        if manifest_rows.empty:
            raise ValueError(f"Runner contract cohort {cohort_id} has no manifest rows in {manifest_name}.")
        manifest_hashes = manifest_rows["record_set_hash"].astype("string").dropna().unique().tolist()
        if manifest_hashes != [str(runner_contract["matched_cohort_hashes"][str(cohort_id)])]:
            raise ValueError(
                f"Runner contract hash mismatch for cohort {cohort_id}: manifest={manifest_hashes}, "
                f"contract={runner_contract['matched_cohort_hashes'][str(cohort_id)]}."
            )
