from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, recall_score
from xgboost import XGBClassifier


PROTOCOL_RUN = Path("Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
TEMPORAL_VIEW = "v2_temporal_mini_3h"
TEMPORAL_TASK = "v2_temporal_3h"
PARTITIONS = ("train", "validation", "test")


def run_layer2_probe(repo_root: Path, seed: int = 20260907) -> dict[str, object]:
    """Run one deliberately narrow XGBoost probe with a matched intervention."""

    manifest_path = repo_root / PROTOCOL_RUN / "primary_protocol/runner/task_training_manifest.parquet"
    manifest = pd.read_parquet(manifest_path)
    target_rows = manifest.loc[
        (manifest["feature_view_id"] == TEMPORAL_VIEW)
        & (manifest["label_task_id"] == TEMPORAL_TASK)
        & manifest["final_trainability"].astype(bool)
        & manifest["partition"].isin(PARTITIONS)
    ].copy()
    target_rows = target_rows[["sample_id", "partition", "target", "fold_id"]].drop_duplicates()
    if target_rows["sample_id"].duplicated().any():
        raise ValueError("Temporal target manifest has duplicate sample IDs.")

    matrix, feature_columns = _load_feature_matrix(manifest, repo_root, TEMPORAL_VIEW, target_rows)
    merged = matrix.merge(target_rows, on="sample_id", how="inner", validate="one_to_one")
    if len(merged) != len(target_rows):
        raise ValueError("Feature/target join did not preserve the temporal target cohort.")

    base_columns = [column for column in feature_columns if "__3h_" not in column]
    derived_columns = [column for column in feature_columns if "__3h_" in column]
    if not base_columns or not derived_columns:
        raise ValueError("Expected both base snapshot and derived 3h feature columns.")

    arms, disruption_audit = _build_arms(merged, feature_columns, base_columns, derived_columns, seed)
    metrics: list[dict[str, object]] = []
    for arm_name, arm_frame in arms.items():
        metrics.extend(_fit_and_score(arm_name, arm_frame, merged, base_columns, seed))
    metrics_frame = pd.DataFrame(metrics).sort_values(["partition", "arm"]).reset_index(drop=True)
    return {
        "metrics": metrics_frame,
        "disruption_audit": disruption_audit,
        "arm_metadata": pd.DataFrame(
            [
                {
                    "arm": "snapshot",
                    "representation": "R_snapshot",
                    "feature_count": len(base_columns),
                    "base_feature_count": len(base_columns),
                    "derived_feature_count": 0,
                },
                {
                    "arm": "causal_history",
                    "representation": "R_history",
                    "feature_count": len(feature_columns),
                    "base_feature_count": len(base_columns),
                    "derived_feature_count": len(derived_columns),
                },
                {
                    "arm": "disrupted_history",
                    "representation": "R_history_disrupted",
                    "feature_count": len(feature_columns),
                    "base_feature_count": len(base_columns),
                    "derived_feature_count": len(derived_columns),
                },
            ]
        ),
        "contract": {
            "status": "diagnostic_layer2_partial",
            "target": "Q10-K3 temporal 3h",
            "feature_view_source": TEMPORAL_VIEW,
            "split": "inherited protocol fold_01",
            "seed": seed,
            "model": "XGBClassifier",
            "n_estimators": 80,
            "max_depth": 3,
            "learning_rate": 0.05,
            "disruption": (
                "Each __3h_ derived column is independently permuted within train, "
                "validation and test partitions; base columns, labels and partitions stay fixed."
            ),
            "training_scope": "one model per arm; no hyperparameter search; no model artifact persisted",
            "not_claimed": [
                "not a benchmark replacement",
                "not evidence of biological correctness",
                "not a multi-fold conclusion",
                "not a full Q/K interaction experiment",
            ],
        },
    }


def _load_feature_matrix(
    manifest: pd.DataFrame,
    repo_root: Path,
    view_id: str,
    target_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    view_rows = manifest.loc[
        (manifest["feature_view_id"] == view_id)
        & manifest["sample_id"].isin(target_rows["sample_id"])
    ]
    if view_rows.empty:
        raise ValueError(f"No feature rows found for {view_id}.")
    row = view_rows.iloc[0]
    matrix_path = _resolve_repo_path(repo_root, Path(str(row["feature_artifact_path"])))
    row_index_path = _resolve_repo_path(repo_root, Path(str(row["row_index_path"])))
    feature_columns = json.loads(str(row["allowed_feature_columns_json"]))
    matrix = pd.read_parquet(matrix_path).reset_index(drop=True)
    row_index = pd.read_parquet(row_index_path).reset_index(drop=True)
    if len(matrix) != len(row_index):
        raise ValueError(f"Feature matrix and row index length mismatch for {view_id}.")
    missing = [column for column in feature_columns if column not in matrix.columns]
    if missing:
        raise ValueError(f"Feature matrix is missing allowed columns: {missing}")
    result = matrix[feature_columns].copy()
    result["sample_id"] = row_index["record.id"].astype(str)
    return result, feature_columns


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _build_arms(
    merged: pd.DataFrame,
    feature_columns: list[str],
    base_columns: list[str],
    derived_columns: list[str],
    seed: int,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    snapshot = merged[base_columns].copy()
    history = merged[feature_columns].copy()
    disrupted = history.copy()
    rng = np.random.default_rng(seed)
    audit_rows: list[dict[str, object]] = []
    for partition in PARTITIONS:
        positions = merged.index[merged["partition"].eq(partition)].to_numpy()
        for column in derived_columns:
            original = disrupted.loc[positions, column].to_numpy(copy=True)
            shuffled = original[rng.permutation(len(original))]
            disrupted.loc[positions, column] = shuffled
            audit_rows.append(
                {
                    "partition": partition,
                    "feature": column,
                    "row_count": len(original),
                    "missing_count": int(pd.isna(original).sum()),
                    "changed_cell_count": int(np.sum(~_equal_with_nan(original, shuffled))),
                    "distribution_preserved": bool(
                        pd.Series(original).isna().sum() == pd.Series(shuffled).isna().sum()
                    ),
                }
            )
    return {
        "snapshot": snapshot,
        "causal_history": history,
        "disrupted_history": disrupted,
    }, pd.DataFrame(audit_rows)


def _equal_with_nan(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return (left == right) | (pd.isna(left) & pd.isna(right))


def _fit_and_score(
    arm_name: str,
    features: pd.DataFrame,
    merged: pd.DataFrame,
    base_columns: list[str],
    seed: int,
) -> list[dict[str, object]]:
    numeric = features.apply(pd.to_numeric, errors="coerce")
    label_names = sorted(merged["target"].astype(str).unique())
    label_to_id = {label: index for index, label in enumerate(label_names)}
    encoded = merged["target"].astype(str).map(label_to_id).to_numpy(dtype=int)
    train_mask = merged["partition"].eq("train").to_numpy()
    model = XGBClassifier(
        n_estimators=80,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="multi:softprob",
        num_class=len(label_names),
        eval_metric="mlogloss",
        random_state=seed,
        n_jobs=2,
        tree_method="hist",
    )
    model.fit(numeric.loc[train_mask], encoded[train_mask])
    predictions = model.predict(numeric).astype(int)
    rows: list[dict[str, object]] = []
    for partition in PARTITIONS:
        mask = merged["partition"].eq(partition).to_numpy()
        rows.append(
            {
                "arm": arm_name,
                "partition": partition,
                "row_count": int(mask.sum()),
                "feature_count": int(numeric.shape[1]),
                "accuracy": float(accuracy_score(encoded[mask], predictions[mask])),
                "balanced_accuracy": float(
                    balanced_accuracy_score(encoded[mask], predictions[mask])
                ),
                "macro_f1": float(
                    f1_score(encoded[mask], predictions[mask], average="macro", zero_division=0)
                ),
                "macro_recall": float(
                    recall_score(encoded[mask], predictions[mask], average="macro", zero_division=0)
                ),
                "class_names": "|".join(label_names),
                "train_rows": int(train_mask.sum()),
            }
        )
    return rows

