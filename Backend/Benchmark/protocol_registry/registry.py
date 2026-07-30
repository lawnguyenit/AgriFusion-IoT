from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256, stable_digest
from Backend.Benchmark.common.provenance import resolve_code_commit
from Backend.Benchmark.protocol_registry.contracts import AuthorizationDecision, ProtocolRegistry
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json


REGISTRY_FILES = {
    "environment_manifest": Path("environment/environment_manifest.csv"),
    "visibility_policy_registry": Path("visibility/visibility_policy_registry.csv"),
    "experiment_arm_manifest": Path("arms/experiment_arm_manifest.csv"),
    "fold_policy_registry": Path("folds/fold_policy_registry.csv"),
    "e1_fold_registry": Path("folds/e1_fold_registry.parquet"),
    "threshold_fit_cohort_manifest": Path("cohorts/threshold_fit_cohort_manifest.parquet"),
    "future_target_policy": Path("future/future_target_policy.csv"),
    "stage_registry": Path("visibility/stage_registry.csv"),
}


def build_protocol_registry(
    config_path: Path,
    canonical_manifest_path: Path,
    *,
    output_root: Path | None = None,
) -> Path:
    config_path = config_path.resolve()
    canonical_manifest_path = canonical_manifest_path.resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Protocol registry config must contain a mapping.")
    _validate_config(payload)

    environment_manifest = pd.DataFrame(payload["environments"]).convert_dtypes()
    environment_manifest["source_manifest_hash"] = file_sha256(canonical_manifest_path)
    environment_manifest["environment_manifest_version"] = str(payload["environment_manifest_version"])
    visibility = pd.DataFrame(payload["visibility_policies"]).convert_dtypes()
    visibility["policy_version"] = str(payload["policy_version"])
    arms = pd.DataFrame(payload["experiment_arms"]).convert_dtypes()
    folds = pd.DataFrame(payload["fold_policies"]).convert_dtypes()
    stages = pd.DataFrame(payload["stages"]).convert_dtypes()
    cohort_manifest = pd.DataFrame(payload["threshold_fit_cohorts"]).convert_dtypes()
    future = pd.DataFrame([payload["future_target_policy"]]).convert_dtypes()
    e1_folds = _build_e1_fold_registry(environment_manifest, folds)

    destination = output_root or Path(__file__).resolve().parent / "artifacts"
    run_id, run_dir = create_run_directory(destination.resolve(), prefix="protocol_registry")
    frames = {
        "environment_manifest": environment_manifest,
        "visibility_policy_registry": visibility,
        "experiment_arm_manifest": arms,
        "fold_policy_registry": folds,
        "e1_fold_registry": e1_folds,
        "threshold_fit_cohort_manifest": cohort_manifest,
        "future_target_policy": future,
        "stage_registry": stages,
    }
    for name, frame in frames.items():
        path = run_dir / REGISTRY_FILES[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False)

    artifact_rows = _artifact_catalog(run_dir, frames)
    artifact_catalog_path = run_dir / "run_metadata" / "artifact_catalog.csv"
    artifact_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(artifact_rows).to_csv(artifact_catalog_path, index=False)
    run_manifest = {
        "pipeline": "protocol_registry",
        "run_id": run_id,
        "protocol_registry_version": str(payload["protocol_registry_version"]),
        "config_path": str(config_path),
        "config_hash": file_sha256(config_path),
        "canonical_manifest_path": str(canonical_manifest_path),
        "canonical_manifest_hash": file_sha256(canonical_manifest_path),
        "registry_contract_hash": stable_digest(
            {
                "environments": payload["environments"],
                "visibility_policies": payload["visibility_policies"],
                "fold_policies": payload["fold_policies"],
                "threshold_fit_cohorts": payload["threshold_fit_cohorts"],
                "future_target_policy": payload["future_target_policy"],
                "experiment_arms": payload["experiment_arms"],
            }
        ),
        "code_commit": resolve_code_commit(Path(__file__).resolve().parents[3]),
        "phase_a_only": True,
        "downstream_runners_unlocked": False,
        "e4_materialized": False,
    }
    write_json(run_dir / "run_metadata" / "run_manifest.json", run_manifest)
    return run_dir


def load_protocol_registry(run_dir: Path) -> ProtocolRegistry:
    run_dir = run_dir.resolve()
    frames: dict[str, pd.DataFrame] = {}
    for name, relative_path in REGISTRY_FILES.items():
        path = run_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Missing protocol registry artifact: {path}")
        frames[name] = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    manifest_path = run_dir / "run_metadata" / "run_manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return ProtocolRegistry(run_dir=run_dir, run_manifest=run_manifest, **frames)


def authorize_operation(
    registry: ProtocolRegistry,
    stage_id: str,
    environment_id: str,
    operation: str,
) -> AuthorizationDecision:
    operation_column = {
        "fit": "fit_allowed",
        "tune": "tuning_allowed",
        "evaluate": "evaluation_allowed",
        "inspect_sensitive": None,
        "inspect_structural": None,
    }.get(operation)
    if operation not in {"fit", "tune", "evaluate", "inspect_sensitive", "inspect_structural"}:
        return AuthorizationDecision(False, stage_id, environment_id, operation, "UNKNOWN", "UNKNOWN_OPERATION")
    rows = registry.visibility_policy_registry.loc[
        (registry.visibility_policy_registry["protocol_stage_id"].astype("string") == stage_id)
        & (registry.visibility_policy_registry["environment_id"].astype("string") == environment_id)
    ]
    if len(rows) != 1:
        return AuthorizationDecision(False, stage_id, environment_id, operation, "UNKNOWN", "POLICY_ROW_NOT_UNIQUE")
    row = rows.iloc[0]
    visibility = str(row["visibility_status"])
    if operation == "inspect_structural":
        allowed = visibility != "NOT_MATERIALIZED"
    elif operation == "inspect_sensitive":
        allowed = visibility in {"FULL", "SOURCE_RELEASED", "EVALUATION_ONLY"}
    else:
        allowed = _as_bool(row[operation_column])
    reason = "AUTHORIZED_BY_VISIBILITY_POLICY" if allowed else "DENIED_BY_VISIBILITY_POLICY"
    return AuthorizationDecision(allowed, stage_id, environment_id, operation, visibility, reason)


def authorize_arm_operation(
    registry: ProtocolRegistry,
    stage_id: str,
    environment_id: str,
    experiment_arm_id: str,
    operation: str,
) -> AuthorizationDecision:
    operation_contract = {
        "label_refit": ("fit", "allow_label_refit"),
        "threshold_refit": ("fit", "allow_threshold_refit"),
        "preprocessing_refit": ("fit", "allow_preprocessing_refit"),
        "model_refit": ("fit", "allow_model_refit"),
        "hyperparameter_refit": ("tune", "allow_hyperparameter_refit"),
        "target_inspection": ("inspect_sensitive", "allow_target_inspection"),
    }
    if operation not in operation_contract:
        return AuthorizationDecision(
            False,
            stage_id,
            environment_id,
            operation,
            "UNKNOWN",
            "UNKNOWN_ARM_OPERATION",
        )
    stage_operation, arm_column = operation_contract[operation]
    stage_decision = authorize_operation(
        registry,
        stage_id,
        environment_id,
        stage_operation,
    )
    if not stage_decision.allowed:
        return AuthorizationDecision(
            False,
            stage_id,
            environment_id,
            operation,
            stage_decision.visibility_status,
            f"STAGE_DENIED:{stage_decision.reason}",
        )
    rows = registry.experiment_arm_manifest.loc[
        (
            registry.experiment_arm_manifest["experiment_arm_id"].astype("string")
            == experiment_arm_id
        )
        & (
            registry.experiment_arm_manifest["environment_id"].astype("string")
            == environment_id
        )
    ]
    if len(rows) != 1:
        return AuthorizationDecision(
            False,
            stage_id,
            environment_id,
            operation,
            stage_decision.visibility_status,
            "ARM_POLICY_ROW_NOT_UNIQUE",
        )
    allowed = _as_bool(rows.iloc[0][arm_column])
    return AuthorizationDecision(
        allowed,
        stage_id,
        environment_id,
        operation,
        stage_decision.visibility_status,
        "AUTHORIZED_BY_STAGE_AND_ARM"
        if allowed
        else "DENIED_BY_EXPERIMENT_ARM",
    )


def _validate_config(payload: dict[str, object]) -> None:
    required = {
        "protocol_registry_version",
        "environment_manifest_version",
        "policy_version",
        "environments",
        "stages",
        "visibility_policies",
        "fold_policies",
        "threshold_fit_cohorts",
        "future_target_policy",
        "experiment_arms",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Protocol config is missing keys: {sorted(missing)}")
    environments = pd.DataFrame(payload["environments"])
    if environments["environment_id"].duplicated().any():
        raise ValueError("environment_id must be unique.")
    intervals: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    for row in environments.itertuples(index=False):
        start = pd.Timestamp(row.start_time)
        end = pd.Timestamp(row.end_time)
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError(f"Invalid environment interval for {row.environment_id}.")
        intervals.append((str(row.environment_id), start, end))
    for index, (left_id, left_start, left_end) in enumerate(intervals):
        for right_id, right_start, right_end in intervals[index + 1 :]:
            if max(left_start, right_start) < min(left_end, right_end):
                raise ValueError(f"Environment intervals overlap: {left_id}, {right_id}.")
    visibility = pd.DataFrame(payload["visibility_policies"])
    if visibility.duplicated(["protocol_stage_id", "environment_id"]).any():
        raise ValueError("Visibility authority must be unique per stage/environment.")
    stages = set(pd.DataFrame(payload["stages"])["protocol_stage_id"].astype(str))
    if not set(visibility["protocol_stage_id"].astype(str)).issubset(stages):
        raise ValueError("Visibility policy references an unknown stage.")
    arms = pd.DataFrame(payload["experiment_arms"])
    if arms.duplicated(["experiment_arm_id", "environment_id"]).any():
        raise ValueError("Experiment arm authority must be unique per arm/environment.")


def _build_e1_fold_registry(environments: pd.DataFrame, policies: pd.DataFrame) -> pd.DataFrame:
    e1 = environments.loc[environments["environment_id"].astype("string") == "E1"].iloc[0]
    e1_start = pd.Timestamp(e1["start_time"])
    e1_end = pd.Timestamp(e1["end_time"])
    rows: list[dict[str, object]] = []
    for policy in policies.to_dict(orient="records"):
        initial_days = int(policy["initial_train_duration_days"])
        validation_days = int(policy["validation_duration_days"])
        test_days = int(policy["test_duration_days"])
        fold_number = 1
        while True:
            train_end = e1_start + pd.Timedelta(days=initial_days + (fold_number - 1) * validation_days)
            validation_end = train_end + pd.Timedelta(days=validation_days)
            test_end = validation_end + pd.Timedelta(days=test_days)
            if train_end >= e1_end:
                break
            complete = test_end <= e1_end
            rows.append(
                {
                    "fold_policy_id": policy["fold_policy_id"],
                    "fold_policy_role": policy["fold_policy_role"],
                    "fold_id": f"fold_{fold_number:02d}",
                    "train_start": e1_start.isoformat(),
                    "train_end": train_end.isoformat(),
                    "train_duration_days": int((train_end - e1_start).days),
                    "validation_start": train_end.isoformat(),
                    "validation_end": min(validation_end, e1_end).isoformat(),
                    "test_start": validation_end.isoformat(),
                    "test_end": min(test_end, e1_end).isoformat(),
                    "requested_test_end": test_end.isoformat(),
                    "purge_3h_min": int(policy["purge_3h_min"]),
                    "purge_8h_min": int(policy["purge_8h_min"]),
                    "fold_status": "COMPLETE" if complete else "PARTIAL_OUTSIDE_E1",
                    "evaluation_usable": complete,
                }
            )
            if not complete:
                break
            fold_number += 1
    return pd.DataFrame(rows).convert_dtypes()


def _artifact_catalog(run_dir: Path, frames: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, frame in frames.items():
        path = run_dir / REGISTRY_FILES[name]
        rows.append(
            {
                "artifact_id": name,
                "relative_path": str(REGISTRY_FILES[name]),
                "row_count": len(frame),
                "column_names": "|".join(frame.columns),
                "file_hash": file_sha256(path),
            }
        )
    return rows


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
