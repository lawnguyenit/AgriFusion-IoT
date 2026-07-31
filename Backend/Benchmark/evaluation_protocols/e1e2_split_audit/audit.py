from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.shared.split_policy import build_split_plan


@dataclass(frozen=True)
class AuditTaskSpec:
    audit_task_id: str
    label_path: str
    label_task_id: str
    label_status_value: str
    required_classes: tuple[str, ...]
    public_scope: str
    horizon_id: str | None = None


TASK_SPECS: tuple[AuditTaskSpec, ...] = (
    AuditTaskSpec(
        audit_task_id="v0_v1_point_train",
        label_path="tasks/point/assignments.parquet",
        label_task_id="point",
        label_status_value="LABELED",
        required_classes=(
            "reference_context_point",
            "low_relative_moisture_point",
            "unresolved_environmental_evidence_point",
        ),
        public_scope="V0 and V1 shared point target",
    ),
    AuditTaskSpec(
        audit_task_id="v2_same_y_3h",
        label_path="tasks/same_y/horizon_3h/assignments.parquet",
        label_task_id="same_y",
        label_status_value="LABELED",
        required_classes=(
            "reference_context_point",
            "low_relative_moisture_point",
            "unresolved_environmental_evidence_point",
        ),
        public_scope="V2 same-Y 3h primary target",
        horizon_id="3h",
    ),
    AuditTaskSpec(
        audit_task_id="v2_same_y_8h",
        label_path="tasks/same_y/horizon_8h/assignments.parquet",
        label_task_id="same_y",
        label_status_value="LABELED",
        required_classes=(
            "reference_context_point",
            "low_relative_moisture_point",
            "unresolved_environmental_evidence_point",
        ),
        public_scope="Optional 8h sensitivity target",
        horizon_id="8h",
    ),
)


def build_e1e2_split_audit(
    *,
    protocol_run_dir: Path,
    native_label_release_dir: Path,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
    split_strategy: str = "chronological_v1",
) -> dict[str, object]:
    artifact_root = protocol_run_dir.parent
    run_id, output_dir = create_run_directory(artifact_root, prefix="e1e2_split_audit")
    env_frame = _load_environment_frame(protocol_run_dir)
    summary_rows: list[dict[str, object]] = []
    class_count_rows: list[dict[str, object]] = []
    environment_count_rows: list[dict[str, object]] = []
    range_rows: list[dict[str, object]] = []

    for task_spec in TASK_SPECS:
        merged = _load_task_frame(
            native_label_release_dir=native_label_release_dir,
            env_frame=env_frame,
            task_spec=task_spec,
        )
        plan = build_split_plan(
            row_count=len(merged),
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            strategy_name=split_strategy,
            timestamps=((merged["timestamp_local"].astype("int64") // 10**9).tolist()),
        )
        partitions = _assign_partitions(merged, plan)
        task_summary, task_class_counts, task_environment_counts, task_ranges = _summarize_task(
            task_spec=task_spec,
            partitions=partitions,
            split_strategy=split_strategy,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )
        summary_rows.append(task_summary)
        class_count_rows.extend(task_class_counts)
        environment_count_rows.extend(task_environment_counts)
        range_rows.extend(task_ranges)

    summary_df = pd.DataFrame(summary_rows).convert_dtypes()
    class_count_df = pd.DataFrame(class_count_rows).convert_dtypes()
    environment_count_df = pd.DataFrame(environment_count_rows).convert_dtypes()
    range_df = pd.DataFrame(range_rows).convert_dtypes()

    summary_df.to_csv(output_dir / "task_split_summary.csv", index=False)
    class_count_df.to_csv(output_dir / "task_partition_class_counts.csv", index=False)
    environment_count_df.to_csv(output_dir / "task_partition_environment_counts.csv", index=False)
    range_df.to_csv(output_dir / "task_partition_ranges.csv", index=False)
    write_text(output_dir / "ARTIFACT_GUIDE.md", _build_artifact_guide() + "\n")
    write_json(
        output_dir / "run_manifest.json",
        {
            "run_id": run_id,
            "protocol_run_dir": str(protocol_run_dir.resolve()),
            "native_label_release_dir": str(native_label_release_dir.resolve()),
            "train_ratio": train_ratio,
            "validation_ratio": validation_ratio,
            "test_ratio": test_ratio,
            "split_strategy": split_strategy,
            "audited_tasks": [task_spec.audit_task_id for task_spec in TASK_SPECS],
        },
    )
    return {
        "run_id": run_id,
        "output_dir": output_dir,
        "summary": summary_df,
        "class_counts": class_count_df,
        "environment_counts": environment_count_df,
        "partition_ranges": range_df,
    }


def _load_environment_frame(protocol_run_dir: Path) -> pd.DataFrame:
    env_path = protocol_run_dir / "domain_manifests" / "sample_environment_manifest.parquet"
    env_frame = pd.read_parquet(env_path).convert_dtypes()
    env_frame["timestamp_local"] = pd.to_datetime(env_frame["timestamp_local"], errors="coerce")
    env_frame = env_frame.loc[env_frame["environment_id"].astype("string").isin(["E1", "E2"])].copy()
    env_frame = env_frame.dropna(subset=["timestamp_local"]).copy()
    return env_frame[["sample_id", "timestamp_local", "environment_id"]].drop_duplicates().reset_index(drop=True)


def _load_task_frame(
    *,
    native_label_release_dir: Path,
    env_frame: pd.DataFrame,
    task_spec: AuditTaskSpec,
) -> pd.DataFrame:
    label_frame = pd.read_parquet(native_label_release_dir / task_spec.label_path).convert_dtypes()
    task_frame = label_frame.loc[
        (label_frame["label_task_id"].astype("string") == task_spec.label_task_id)
        & (label_frame["label_status"].astype("string") == task_spec.label_status_value)
    ].copy()
    if task_spec.horizon_id is not None and "horizon_id" in label_frame.columns:
        task_frame = task_frame.loc[task_frame["horizon_id"].astype("string") == task_spec.horizon_id].copy()
    merged = env_frame.merge(
        task_frame[["sample_id", "label_name"]],
        on="sample_id",
        how="inner",
        validate="one_to_one",
    )
    merged = merged.rename(columns={"label_name": "target"}).copy()
    merged = merged.sort_values(["timestamp_local", "sample_id"], kind="stable").reset_index(drop=True)
    return merged


def _assign_partitions(task_frame: pd.DataFrame, plan) -> pd.DataFrame:
    partitions: list[pd.DataFrame] = []
    for segment in plan.segments:
        frame = task_frame.iloc[segment.start : segment.stop].copy()
        frame["partition"] = segment.name
        partitions.append(frame)
    return pd.concat(partitions, ignore_index=True).convert_dtypes()


def _summarize_task(
    *,
    task_spec: AuditTaskSpec,
    partitions: pd.DataFrame,
    split_strategy: str,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    class_count_rows: list[dict[str, object]] = []
    environment_count_rows: list[dict[str, object]] = []
    range_rows: list[dict[str, object]] = []
    required_classes = set(task_spec.required_classes)
    partitions_with_full_support = 0
    missing_classes_by_partition: dict[str, list[str]] = {}

    for partition_name in ("train", "validation", "test"):
        frame = partitions.loc[partitions["partition"].astype("string") == partition_name].copy()
        observed_classes = set(frame["target"].astype("string").dropna().tolist())
        missing = sorted(required_classes - observed_classes)
        missing_classes_by_partition[partition_name] = missing
        if not missing:
            partitions_with_full_support += 1

        for target, count in (
            frame.groupby("target", dropna=False).size().reset_index(name="row_count").itertuples(index=False)
            if not frame.empty
            else []
        ):
            class_count_rows.append(
                {
                    "audit_task_id": task_spec.audit_task_id,
                    "public_scope": task_spec.public_scope,
                    "partition": partition_name,
                    "target": target,
                    "row_count": int(count),
                }
            )
        for environment_id, count in (
            frame.groupby("environment_id", dropna=False).size().reset_index(name="row_count").itertuples(index=False)
            if not frame.empty
            else []
        ):
            environment_count_rows.append(
                {
                    "audit_task_id": task_spec.audit_task_id,
                    "public_scope": task_spec.public_scope,
                    "partition": partition_name,
                    "environment_id": environment_id,
                    "row_count": int(count),
                }
            )
        range_rows.append(
            {
                "audit_task_id": task_spec.audit_task_id,
                "public_scope": task_spec.public_scope,
                "partition": partition_name,
                "row_count": int(len(frame)),
                "timestamp_start": None if frame.empty else frame["timestamp_local"].iloc[0].isoformat(),
                "timestamp_end": None if frame.empty else frame["timestamp_local"].iloc[-1].isoformat(),
                "missing_required_classes_json": json.dumps(missing, ensure_ascii=True, separators=(",", ":")),
            }
        )

    summary_row = {
        "audit_task_id": task_spec.audit_task_id,
        "public_scope": task_spec.public_scope,
        "split_strategy": split_strategy,
        "train_ratio": train_ratio,
        "validation_ratio": validation_ratio,
        "test_ratio": test_ratio,
        "total_rows": int(len(partitions)),
        "required_classes_json": json.dumps(sorted(required_classes), ensure_ascii=True, separators=(",", ":")),
        "train_has_full_class_support": len(missing_classes_by_partition["train"]) == 0,
        "validation_has_full_class_support": len(missing_classes_by_partition["validation"]) == 0,
        "test_has_full_class_support": len(missing_classes_by_partition["test"]) == 0,
        "all_partitions_have_full_class_support": partitions_with_full_support == 3,
        "train_missing_classes_json": json.dumps(
            missing_classes_by_partition["train"], ensure_ascii=True, separators=(",", ":")
        ),
        "validation_missing_classes_json": json.dumps(
            missing_classes_by_partition["validation"], ensure_ascii=True, separators=(",", ":")
        ),
        "test_missing_classes_json": json.dumps(
            missing_classes_by_partition["test"], ensure_ascii=True, separators=(",", ":")
        ),
    }
    return summary_row, class_count_rows, environment_count_rows, range_rows


def _build_artifact_guide() -> str:
    return "\n".join(
        [
            "# E1+E2 Split Audit Guide",
            "",
            "## Input",
            "- one `evaluation_protocols` run for `E1/E2` timestamps and environment assignment",
            "- one `weak_labels` run for current public point and `v2 same-Y` label tasks",
            "",
            "## This Audit Does",
            "- merges `E1` and `E2` into one chronological source lane",
            "- applies a contiguous `70/15/15` split using the shared benchmark split policy",
            "- checks whether `train`, `validation`, and `test` each keep all required classes",
            "",
            "## Output",
            "- `task_split_summary.csv`: pass/fail by audited task",
            "- `task_partition_class_counts.csv`: class counts by partition",
            "- `task_partition_environment_counts.csv`: `E1` versus `E2` mix by partition",
            "- `task_partition_ranges.csv`: timestamp coverage and missing-class notes",
        ]
    )
