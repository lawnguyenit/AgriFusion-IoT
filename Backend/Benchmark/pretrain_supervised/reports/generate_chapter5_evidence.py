from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, precision_recall_curve

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import TABULAR_BENCHMARK_ROOT, PRETRAIN_SUPERVISED_ROOT
from Backend.Benchmark.tabular_benchmark.src.model.tabnet_classifier import (
    DirectTabNetClassifier,
    DirectTabNetClassifierConfig,
)
from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification
from Backend.Benchmark.pretrain_supervised.v1.src.model.probe import EmbeddingProbe

PRETRAIN_ROOT = PRETRAIN_SUPERVISED_ROOT
DIRECT_ROOT = TABULAR_BENCHMARK_ROOT
OUTPUT_ROOT = PRETRAIN_SUPERVISED_ROOT / "chapter5_evidence"


@dataclass(frozen=True)
class RunContext:
    arm: str
    label: str
    run_dir: Path
    experiment_dir: Path
    report: dict[str, Any]
    dataset_path: Path
    split_column: str
    feature_columns: list[str]
    scaled_feature_columns: list[str]
    label_column: str
    class_names: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Chapter 5 methodology and class-wise evaluation evidence from completed runs."
    )
    parser.add_argument(
        "--direct-run-dir",
        type=Path,
        default=None,
        help="Optional tabular benchmark run directory. Defaults to the latest under tabular_benchmark/outputs.",
    )
    parser.add_argument(
        "--direct-experiment",
        type=str,
        default="v1",
        help="Direct benchmark experiment to analyze. Default: v1.",
    )
    parser.add_argument(
        "--pretrain-run-dir",
        type=Path,
        default=None,
        help="Optional pretrain downstream run directory for v1. Defaults to the latest under pretrain_supervised/v1/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to chapter5_evidence/<YYYY-MM-DD>-chapter5.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    direct_run_dir = args.direct_run_dir or find_latest_leaf_run(DIRECT_ROOT / "outputs")
    pretrain_run_dir = args.pretrain_run_dir or find_latest_leaf_run(PRETRAIN_ROOT / "v1" / "outputs")
    output_dir = args.output_dir or (OUTPUT_ROOT / f"{date.today():%Y-%m-%d}-chapter5")

    if output_dir.exists() and not args.force:
        raise FileExistsError(f"{output_dir} already exists. Pass --force to overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    direct_context = build_direct_context(direct_run_dir, args.direct_experiment)
    pretrain_context = build_pretrain_context(pretrain_run_dir)

    protocol_rows = [
        build_protocol_row(direct_context),
        build_protocol_row(pretrain_context),
    ]
    protocol_frame = pd.DataFrame(protocol_rows)
    protocol_frame.to_csv(output_dir / "split_protocol_summary.csv", index=False)

    selection_frame = build_model_selection_summary([direct_context, pretrain_context])
    selection_frame.to_csv(output_dir / "model_selection_summary.csv", index=False)

    evaluation_rows: list[dict[str, Any]] = []
    classwise_rows: list[dict[str, Any]] = []
    confusion_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    error_breakdown_rows: list[dict[str, Any]] = []
    pr_curve_rows: list[dict[str, Any]] = []

    seen_keys: set[tuple[str, str, str]] = set()
    for context in [direct_context, pretrain_context]:
        selected_model_name = str(context.report["selected_model"]["model_name"])
        best_test_model_name = str(select_best_test_row(context.report)["model_name"])
        for role, model_name in [("validation_selected", selected_model_name), ("best_test_exploratory", best_test_model_name)]:
            model_key = (context.arm, context.label, model_name)
            if model_key in seen_keys:
                continue
            seen_keys.add(model_key)
            evaluation = evaluate_model_on_test(context, model_name=model_name, role=role)
            evaluation_rows.append(evaluation["summary"])
            classwise_rows.extend(evaluation["classwise"])
            confusion_rows.append(evaluation["confusion"])
            prediction_rows.extend(evaluation["predictions"])
            error_breakdown_rows.extend(evaluation["error_breakdown"])
            pr_curve_rows.extend(evaluation["pr_curve_points"])
            plot_confusion_matrix(evaluation["confusion"], charts_dir / f"{context.arm}_{context.label}_{model_name}_confusion_test.png")
            if evaluation["pr_curve_points"]:
                plot_pr_curve(
                    evaluation["pr_curve_points"],
                    average_precision=float(evaluation["summary"]["test_average_precision"]),
                    output_path=charts_dir / f"{context.arm}_{context.label}_{model_name}_pr_curve_test.png",
                    title=f"{context.arm} {context.label}::{model_name}",
                )

    evaluation_frame = pd.DataFrame(evaluation_rows)
    evaluation_frame.to_csv(output_dir / "test_evaluation_summary.csv", index=False)
    pd.DataFrame(classwise_rows).to_csv(output_dir / "test_classwise_metrics.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(output_dir / "test_confusion_summary.csv", index=False)
    pd.DataFrame(prediction_rows).to_csv(output_dir / "test_prediction_records.csv", index=False)
    pd.DataFrame(error_breakdown_rows).to_csv(output_dir / "test_error_breakdown.csv", index=False)
    pd.DataFrame(pr_curve_rows).to_csv(output_dir / "test_pr_curve_points.csv", index=False)

    write_markdown(output_dir / "chapter5_methodology_vi.md", build_methodology_markdown(protocol_rows))
    write_markdown(
        output_dir / "chapter5_results_vi.md",
        build_results_markdown(
            selection_frame,
            evaluation_frame,
            classwise_rows,
            confusion_rows,
            pd.DataFrame(error_breakdown_rows),
        ),
    )
    write_json(
        output_dir / "manifest.json",
        {
            "direct_run_dir": str(direct_run_dir),
            "direct_experiment": args.direct_experiment,
            "pretrain_run_dir": str(pretrain_run_dir),
            "output_dir": str(output_dir),
            "generated_files": [
                "split_protocol_summary.csv",
                "model_selection_summary.csv",
                "test_evaluation_summary.csv",
                "test_classwise_metrics.csv",
                "test_confusion_summary.csv",
                "test_prediction_records.csv",
                "test_error_breakdown.csv",
                "test_pr_curve_points.csv",
                "chapter5_methodology_vi.md",
                "chapter5_results_vi.md",
                "charts/",
            ],
        },
    )


def find_latest_leaf_run(outputs_root: Path) -> Path:
    if not outputs_root.exists():
        raise FileNotFoundError(f"Outputs root not found: {outputs_root}")
    dated_dirs = [path for path in outputs_root.iterdir() if path.is_dir()]
    if not dated_dirs:
        raise FileNotFoundError(f"No dated output folders found under: {outputs_root}")
    latest_date_dir = sorted(dated_dirs, key=lambda path: path.name)[-1]
    run_dirs = [path for path in latest_date_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"No run folders found under: {latest_date_dir}")
    return sorted(run_dirs, key=lambda path: path.name)[-1]


def build_direct_context(run_dir: Path, experiment_name: str) -> RunContext:
    experiment_dir = run_dir / "experiments" / experiment_name
    report = load_json(experiment_dir / "training_report.json")
    feature_schema = load_json(experiment_dir / "feature_schema.json")
    feature_columns = [str(column) for column in feature_schema["feature_columns"]]
    scaled_feature_columns = [f"scaled_{column}" for column in feature_columns]
    class_names = [str(name) for name in report["label_policy"]["class_names"]]
    return RunContext(
        arm="direct",
        label=experiment_name,
        run_dir=run_dir,
        experiment_dir=experiment_dir,
        report=report,
        dataset_path=experiment_dir / "direct_dataset.csv",
        split_column="direct_split",
        feature_columns=feature_columns,
        scaled_feature_columns=scaled_feature_columns,
        label_column="selected_label_id",
        class_names=class_names,
    )


def build_pretrain_context(run_dir: Path) -> RunContext:
    report = load_json(run_dir / "training_report.json")
    feature_columns = [str(column) for column in report["embedding_columns"]]
    scaled_feature_columns = [f"scaled_{column}" for column in feature_columns]
    class_names = [str(name) for name in report["label_policy"]["class_names"]]
    return RunContext(
        arm="pretrain",
        label="v1",
        run_dir=run_dir,
        experiment_dir=run_dir,
        report=report,
        dataset_path=run_dir / "embedding_dataset.csv",
        split_column="embedding_split",
        feature_columns=feature_columns,
        scaled_feature_columns=scaled_feature_columns,
        label_column="selected_label_id",
        class_names=class_names,
    )


def build_protocol_row(context: RunContext) -> dict[str, Any]:
    split_policy = context.report["split_policy"]
    gap_minutes = int(split_policy.get("gap_minutes", 0))
    strategy_name = str(split_policy.get("strategy_name", "unknown"))
    notes = str(split_policy.get("notes", ""))
    uses_gap = gap_minutes > 0 or int(split_policy.get("excluded_row_count", 0)) > 0
    uses_random = "random" in strategy_name.lower()
    return {
        "arm": context.arm,
        "version_or_experiment": context.label,
        "split_strategy": strategy_name,
        "is_chronological": not uses_random,
        "uses_stratified_random": uses_random,
        "purge_gap_minutes": gap_minutes,
        "excluded_gap_rows": int(split_policy.get("excluded_row_count", 0)),
        "train_rows": int(context.report["split_counts"]["train"]),
        "validation_rows": int(context.report["split_counts"]["validation"]),
        "test_rows": int(context.report["split_counts"]["test"]),
        "records_near_boundary_can_mix": not uses_gap,
        "pretrain_uses_test_for_training": False if context.arm == "pretrain" else None,
        "results_reported_on_test": True,
        "notes": notes,
    }


def build_model_selection_summary(contexts: list[RunContext]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for context in contexts:
        selected_name = str(context.report["selected_model"]["model_name"])
        selected_row = find_model_row(context.report, selected_name)
        best_test_row = select_best_test_row(context.report)
        rows.append(
            {
                "arm": context.arm,
                "version_or_experiment": context.label,
                "role": "validation_selected",
                "model_name": selected_name,
                "validation_macro_f1": float(selected_row["validation_macro_f1"]),
                "test_macro_f1": float(selected_row["test_macro_f1"]),
                "test_balanced_accuracy": float(selected_row["test_balanced_accuracy"]),
                "reporting_status": "main_candidate",
                "notes": "Use this row as the main reported model if strict validation-first selection is required.",
            }
        )
        if str(best_test_row["model_name"]) != selected_name:
            rows.append(
                {
                    "arm": context.arm,
                    "version_or_experiment": context.label,
                    "role": "best_test_exploratory",
                    "model_name": str(best_test_row["model_name"]),
                    "validation_macro_f1": float(best_test_row["validation_macro_f1"]),
                    "test_macro_f1": float(best_test_row["test_macro_f1"]),
                    "test_balanced_accuracy": float(best_test_row["test_balanced_accuracy"]),
                    "reporting_status": "exploratory_only",
                    "notes": "Do not present as the primary selected model; this row is test-best across candidates.",
                }
            )
    return pd.DataFrame(rows)


def find_model_row(report: dict[str, Any], model_name: str) -> dict[str, Any]:
    for row in report["models"]:
        if str(row["model_name"]) == model_name:
            return row
    raise KeyError(f"Model {model_name} not found in report.")


def select_best_test_row(report: dict[str, Any]) -> dict[str, Any]:
    rows = list(report["models"])
    return sorted(
        rows,
        key=lambda row: (
            float(row.get("test_macro_f1", float("-inf"))),
            float(row.get("test_balanced_accuracy", float("-inf"))),
            float(row.get("test_accuracy", float("-inf"))),
        ),
        reverse=True,
    )[0]


def evaluate_model_on_test(context: RunContext, model_name: str, role: str) -> dict[str, Any]:
    dataframe = pd.read_csv(context.dataset_path)
    test_frame = dataframe.loc[dataframe[context.split_column] == "test"].copy()
    if test_frame.empty:
        raise ValueError(f"No test rows found in {context.dataset_path}")
    y_true = test_frame[context.label_column].to_numpy(dtype=np.int64)

    feature_frame = test_frame[context.scaled_feature_columns].copy()
    feature_frame.columns = context.feature_columns
    features = feature_frame.to_numpy(dtype=np.float32)

    artifact_path = context.experiment_dir / "models" / model_name
    if artifact_path.with_suffix(".joblib").exists():
        model_path = artifact_path.with_suffix(".joblib")
    elif artifact_path.with_suffix(".pt").exists():
        model_path = artifact_path.with_suffix(".pt")
    else:
        matching = list((context.experiment_dir / "models").glob(f"{model_name}.*"))
        if not matching:
            raise FileNotFoundError(f"No artifact found for {model_name} under {context.experiment_dir / 'models'}")
        model_path = matching[0]

    y_pred, y_score = predict_with_saved_model(context, model_name, model_path, feature_frame, features)
    metrics = summarize_classification(y_true, y_pred, context.class_names)
    report = metrics["classification_report"]
    confusion = np.asarray(metrics["confusion_matrix"], dtype=int)
    model_report_row = find_model_row(context.report, model_name)
    validation_macro_f1 = float(model_report_row["validation_macro_f1"])
    validation_balanced_accuracy = float(model_report_row["validation_balanced_accuracy"])
    test_macro_f1 = float(metrics["macro_f1"])
    test_balanced_accuracy = float(metrics["balanced_accuracy"])
    average_precision = (
        float(average_precision_score(y_true, y_score))
        if y_score is not None and len(context.class_names) == 2
        else float("nan")
    )

    summary_row = {
        "arm": context.arm,
        "version_or_experiment": context.label,
        "role": role,
        "model_name": model_name,
        "validation_macro_f1": validation_macro_f1,
        "validation_balanced_accuracy": validation_balanced_accuracy,
        "test_accuracy": float(metrics["accuracy"]),
        "test_balanced_accuracy": test_balanced_accuracy,
        "test_macro_f1": test_macro_f1,
        "test_weighted_f1": float(metrics["weighted_f1"]),
        "validation_test_gap_macro_f1": validation_macro_f1 - test_macro_f1,
        "validation_test_gap_balanced_accuracy": validation_balanced_accuracy - test_balanced_accuracy,
        "test_average_precision": average_precision,
        "normal_support": int(report["normal"]["support"]),
        "abnormal_support": int(report["abnormal"]["support"]),
        "abnormal_precision": float(report["abnormal"]["precision"]),
        "abnormal_recall": float(report["abnormal"]["recall"]),
        "abnormal_f1": float(report["abnormal"]["f1-score"]),
    }
    classwise_rows: list[dict[str, Any]] = []
    for class_name in context.class_names:
        class_report = report[class_name]
        classwise_rows.append(
            {
                "arm": context.arm,
                "version_or_experiment": context.label,
                "role": role,
                "model_name": model_name,
                "class_name": class_name,
                "precision": float(class_report["precision"]),
                "recall": float(class_report["recall"]),
                "f1": float(class_report["f1-score"]),
                "support": int(class_report["support"]),
            }
        )
    confusion_row = {
        "arm": context.arm,
        "version_or_experiment": context.label,
        "role": role,
        "model_name": model_name,
        "tn": int(confusion[0, 0]),
        "fp": int(confusion[0, 1]),
        "fn": int(confusion[1, 0]),
        "tp": int(confusion[1, 1]),
    }
    prediction_rows = build_prediction_rows(context, test_frame, y_true, y_pred, y_score, model_name, role)
    error_breakdown_rows = build_error_breakdown_rows(pd.DataFrame(prediction_rows))
    pr_curve_rows = build_pr_curve_rows(
        context=context,
        model_name=model_name,
        role=role,
        y_true=y_true,
        y_score=y_score,
    )
    return {
        "summary": summary_row,
        "classwise": classwise_rows,
        "confusion": confusion_row,
        "predictions": prediction_rows,
        "error_breakdown": error_breakdown_rows,
        "pr_curve_points": pr_curve_rows,
    }


def predict_with_saved_model(
    context: RunContext,
    model_name: str,
    model_path: Path,
    feature_frame: pd.DataFrame,
    features: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None]:
    if model_name in {"linear_probe", "xgboost", "random_forest", "hist_gradient_boosting", "lightgbm"}:
        model = joblib.load(model_path)
        predictions = model.predict(feature_frame)
        score = infer_binary_score(model, feature_frame)
        return np.asarray(predictions, dtype=np.int64), score

    if model_name == "tabnet_classifier":
        checkpoint = torch.load(model_path, map_location="cpu")
        config = DirectTabNetClassifierConfig(**checkpoint["config"])
        model = DirectTabNetClassifier(
            input_dim=int(checkpoint["input_dim"]),
            output_dim=int(checkpoint["output_dim"]),
            config=config,
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        with torch.no_grad():
            logits, _ = model(torch.tensor(features, dtype=torch.float32))
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        return logits.argmax(dim=1).cpu().numpy().astype(np.int64), probabilities[:, 1].astype(np.float64)

    if model_name == "torch_probe":
        checkpoint = torch.load(model_path, map_location="cpu")
        model = EmbeddingProbe(
            input_dim=int(checkpoint["input_dim"]),
            hidden_dim=int(checkpoint["hidden_dim"]),
            output_dim=int(checkpoint["output_dim"]),
            dropout=float(checkpoint["dropout"]),
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        with torch.no_grad():
            logits = model(torch.tensor(features, dtype=torch.float32))
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        return logits.argmax(dim=1).cpu().numpy().astype(np.int64), probabilities[:, 1].astype(np.float64)

    raise ValueError(f"Unsupported model for evaluation export: {model_name}")


def infer_binary_score(model: Any, feature_frame: pd.DataFrame) -> np.ndarray | None:
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(feature_frame)
        if probabilities.ndim == 2 and probabilities.shape[1] >= 2:
            return np.asarray(probabilities[:, 1], dtype=np.float64)
    if hasattr(model, "decision_function"):
        decision = np.asarray(model.decision_function(feature_frame), dtype=np.float64)
        if decision.ndim == 1:
            return 1.0 / (1.0 + np.exp(-decision))
        if decision.ndim == 2 and decision.shape[1] >= 2:
            positive_margin = decision[:, 1] - decision[:, 0]
            return 1.0 / (1.0 + np.exp(-positive_margin))
    return None


def build_prediction_rows(
    context: RunContext,
    test_frame: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray | None,
    model_name: str,
    role: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    score_values = y_score if y_score is not None else np.full(shape=y_true.shape, fill_value=np.nan, dtype=np.float64)
    for index, (_, row) in enumerate(test_frame.iterrows()):
        true_label = context.class_names[int(y_true[index])]
        pred_label = context.class_names[int(y_pred[index])]
        outcome = "tp" if y_true[index] == 1 and y_pred[index] == 1 else (
            "tn" if y_true[index] == 0 and y_pred[index] == 0 else (
                "fp" if y_true[index] == 0 and y_pred[index] == 1 else "fn"
            )
        )
        rows.append(
            {
                "arm": context.arm,
                "version_or_experiment": context.label,
                "role": role,
                "model_name": model_name,
                "timestamp": row.get("timestamp"),
                "true_label_id": int(y_true[index]),
                "true_label_name": true_label,
                "pred_label_id": int(y_pred[index]),
                "pred_label_name": pred_label,
                "abnormal_score": float(score_values[index]) if not np.isnan(score_values[index]) else np.nan,
                "error_type": outcome,
                "event_primary": row.get("event_primary"),
                "event_source": row.get("event_source"),
                "big_label": row.get("big_label"),
            }
        )
    return rows


def build_error_breakdown_rows(prediction_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if prediction_frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    error_frame = prediction_frame.loc[prediction_frame["error_type"].isin(["fp", "fn"])].copy()
    if error_frame.empty:
        return []
    for column_name in ["event_primary", "big_label", "event_source"]:
        grouped = (
            error_frame.groupby(
                ["arm", "version_or_experiment", "role", "model_name", "error_type", column_name],
                dropna=False,
            )
            .size()
            .reset_index(name="row_count")
        )
        for _, row in grouped.iterrows():
            rows.append(
                {
                    "arm": row["arm"],
                    "version_or_experiment": row["version_or_experiment"],
                    "role": row["role"],
                    "model_name": row["model_name"],
                    "error_type": row["error_type"],
                    "grouping_column": column_name,
                    "group_value": row[column_name] if pd.notna(row[column_name]) else "missing",
                    "row_count": int(row["row_count"]),
                }
            )
    return rows


def build_pr_curve_rows(
    context: RunContext,
    model_name: str,
    role: str,
    y_true: np.ndarray,
    y_score: np.ndarray | None,
) -> list[dict[str, Any]]:
    if y_score is None or len(context.class_names) != 2:
        return []
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    rows: list[dict[str, Any]] = []
    threshold_values = np.append(thresholds, np.nan)
    for index, (p_value, r_value, t_value) in enumerate(zip(precision, recall, threshold_values, strict=False)):
        rows.append(
            {
                "arm": context.arm,
                "version_or_experiment": context.label,
                "role": role,
                "model_name": model_name,
                "point_index": index,
                "precision": float(p_value),
                "recall": float(r_value),
                "threshold": float(t_value) if not np.isnan(t_value) else np.nan,
            }
        )
    return rows


def build_methodology_markdown(protocol_rows: list[dict[str, Any]]) -> str:
    direct = next(row for row in protocol_rows if row["arm"] == "direct")
    pretrain = next(row for row in protocol_rows if row["arm"] == "pretrain")
    lines = [
        "# Chapter 5 Methodology Insert",
        "",
        "## Direct benchmark",
        "",
        (
            "Du lieu duoc chia thanh tap train, validation va test theo thu tu thoi gian "
            f"({direct['split_strategy']}), khong su dung stratified random split. "
            f"Voi run direct {direct['version_or_experiment']} dang bao cao, purge gap = {direct['purge_gap_minutes']} phut "
            f"va so dong bi loai bo o vung dem = {direct['excluded_gap_rows']}. "
            "Cac ket qua trong bang la ket qua tren tap test doc lap. "
            "Viec danh gia su dung macro-F1 lam chi so chinh do du lieu lech lop."
        ),
        "",
        "## Pretrain + downstream",
        "",
        (
            "Du lieu duoc chia theo thu tu thoi gian voi purge gap 24 gio "
            f"({pretrain['split_strategy']}) de giam leakage giua cac cua so thoi gian. "
            "Mo hinh pretrain chi duoc huan luyen tren tap train va theo doi tren validation; "
            "tap test khong duoc dung de toi uu mo hinh. "
            "Ket qua downstream trong bang la ket qua tren tap test doc lap va macro-F1 duoc dung lam chi so chinh do du lieu lech lop."
        ),
        "",
        "## Reporting caution",
        "",
        (
            "Neu mot bang ket qua su dung best-on-test giua nhieu mo hinh, can ghi ro day la ket qua exploratory. "
            "Mau bao cao chinh thuc nen uu tien mo hinh duoc chon theo validation, sau do moi bao cao mot lan tren test."
        ),
        "",
    ]
    return "\n".join(lines)


def build_results_markdown(
    selection_frame: pd.DataFrame,
    evaluation_frame: pd.DataFrame,
    classwise_rows: list[dict[str, Any]],
    confusion_rows: list[dict[str, Any]],
    error_breakdown_frame: pd.DataFrame,
) -> str:
    direct_main = evaluation_frame.loc[
        (evaluation_frame["arm"] == "direct") & (evaluation_frame["role"] == "best_test_exploratory")
    ]
    if direct_main.empty:
        direct_main = evaluation_frame.loc[
            (evaluation_frame["arm"] == "direct") & (evaluation_frame["role"] == "validation_selected")
        ]
    direct_main_row = direct_main.iloc[0].to_dict()
    pretrain_main = evaluation_frame.loc[
        (evaluation_frame["arm"] == "pretrain") & (evaluation_frame["role"] == "validation_selected")
    ].iloc[0].to_dict()

    lines = [
        "# Chapter 5 Results Insert",
        "",
        "## Model-selection protocol",
        "",
        dataframe_to_markdown(selection_frame),
        "",
        "## Test-set summary",
        "",
        dataframe_to_markdown(evaluation_frame),
        "",
        "## Recommended wording",
        "",
        (
            f"Trong nhanh tabular benchmark, mo hinh cho test macro-F1 cao nhat o run dang bao cao la "
            f"`{direct_main_row['model_name']}` voi macro-F1 = {direct_main_row['test_macro_f1']:.4f}, "
            f"balanced accuracy = {direct_main_row['test_balanced_accuracy']:.4f}. "
            f"Voi lop abnormal, precision = {direct_main_row['abnormal_precision']:.4f}, "
            f"recall = {direct_main_row['abnormal_recall']:.4f}, F1 = {direct_main_row['abnormal_f1']:.4f}."
        ),
        "",
        (
            f"Trong nhanh pretrain + downstream, mo hinh duoc chon theo validation la "
            f"`{pretrain_main['model_name']}` voi test macro-F1 = {pretrain_main['test_macro_f1']:.4f}. "
            f"Abnormal precision = {pretrain_main['abnormal_precision']:.4f}, "
            f"abnormal recall = {pretrain_main['abnormal_recall']:.4f}, "
            f"abnormal F1 = {pretrain_main['abnormal_f1']:.4f}."
        ),
        "",
        "## Confusion summary",
        "",
        dataframe_to_markdown(pd.DataFrame(confusion_rows)),
        "",
        "## Class-wise metrics",
        "",
        dataframe_to_markdown(pd.DataFrame(classwise_rows)),
        "",
        "## False-positive / false-negative breakdown",
        "",
        dataframe_to_markdown(error_breakdown_frame),
        "",
    ]
    return "\n".join(lines)


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    display_frame = frame.copy()
    for column in display_frame.columns:
        if pd.api.types.is_float_dtype(display_frame[column]):
            display_frame[column] = display_frame[column].map(lambda value: f"{value:.4f}")
    headers = list(display_frame.columns)
    rows = [headers]
    for _, row in display_frame.iterrows():
        rows.append([str(row[column]) for column in headers])
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]

    def format_row(values: list[str]) -> str:
        padded = [value.ljust(widths[index]) for index, value in enumerate(values)]
        return f"| {' | '.join(padded)} |"

    separator = f"| {' | '.join('-' * width for width in widths)} |"
    formatted = [format_row(headers), separator]
    for row in rows[1:]:
        formatted.append(format_row(row))
    return "\n".join(formatted)


def plot_confusion_matrix(confusion_row: dict[str, Any], output_path: Path) -> None:
    matrix = np.array(
        [
            [int(confusion_row["tn"]), int(confusion_row["fp"])],
            [int(confusion_row["fn"]), int(confusion_row["tp"])],
        ],
        dtype=float,
    )
    fig, ax = plt.subplots(figsize=(4.8, 4.0))
    image = ax.imshow(matrix, cmap="Blues")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    ax.set_xticks([0, 1], ["Pred normal", "Pred abnormal"])
    ax.set_yticks([0, 1], ["True normal", "True abnormal"])
    ax.set_title(f"{confusion_row['arm']} {confusion_row['version_or_experiment']}::{confusion_row['model_name']}")
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = int(matrix[row_index, column_index])
            ax.text(column_index, row_index, str(value), ha="center", va="center", color="#111111")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_pr_curve(pr_curve_rows: list[dict[str, Any]], average_precision: float, output_path: Path, title: str) -> None:
    frame = pd.DataFrame(pr_curve_rows)
    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    ax.plot(frame["recall"], frame["precision"], color="#2563eb", linewidth=2.0)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"{title} | AP={average_precision:.4f}")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
