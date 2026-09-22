"""Paired analysis for causal online versus retrospective event targets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.weak_labels.analysis.temporal_target_views import Y_EVENT, Y_ONLINE
from Backend.Benchmark.weak_labels.infrastructure.hashing import file_sha256


@dataclass(frozen=True)
class EventOnlineComparisonResult:
    run_id: str
    output_dir: Path
    g_total_count: int
    g_evaluable_count: int
    g_unique_evaluable_count: int
    metric_row_count: int


def build_event_online_comparison(
    *,
    model_suite_run_dir: Path,
    target_views_artifact_dir: Path,
    output_root: Path,
    profile_name: str = "temporal_event_online_3h",
) -> EventOnlineComparisonResult:
    model_suite_run_dir = model_suite_run_dir.resolve()
    target_views_artifact_dir = target_views_artifact_dir.resolve()
    prediction_path = model_suite_run_dir / "profiles" / profile_name / "per_sample_predictions.csv"
    target_path = target_views_artifact_dir / "target_views_assignments.parquet"
    if not prediction_path.exists():
        raise FileNotFoundError(f"Model prediction artifact is missing: {prediction_path}")
    if not target_path.exists():
        raise FileNotFoundError(f"Target-view artifact is missing: {target_path}")

    predictions = pd.read_csv(prediction_path).convert_dtypes()
    targets = pd.read_parquet(target_path).convert_dtypes()
    _assert_prediction_contract(predictions)
    g = _load_g_cohort(targets)
    paired_predictions = _join_g_predictions(g, predictions)
    metrics, per_class = _build_metrics(paired_predictions)
    transitions = _build_transitions(paired_predictions)

    run_id, output_dir = create_run_directory(
        output_root.resolve(), prefix="temporal_event_online_comparison"
    )
    paired_path = output_dir / "paired_target_predictions.parquet"
    metrics_path = output_dir / "paired_target_metrics.csv"
    per_class_path = output_dir / "paired_target_per_class_metrics.csv"
    transitions_path = output_dir / "paired_prediction_transitions.csv"
    chart_path = output_dir / "g_semantics_accuracy.png"
    paired_predictions.to_parquet(paired_path, index=False)
    metrics.to_csv(metrics_path, index=False)
    per_class.to_csv(per_class_path, index=False)
    transitions.to_csv(transitions_path, index=False)
    _write_accuracy_chart(metrics, chart_path)

    manifest = {
        "artifact_type": "PAIRED_EVENT_ONLINE_MODEL_COMPARISON",
        "artifact_status": "DERIVED_ANALYSIS_ONLY",
        "authority_status": "CANDIDATE_REFERENCE_ONLY",
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_suite_run_dir": str(model_suite_run_dir),
        "model_prediction_path": str(prediction_path),
        "model_prediction_hash": file_sha256(prediction_path),
        "target_views_artifact_dir": str(target_views_artifact_dir),
        "target_views_assignments_path": str(target_path),
        "target_views_assignments_hash": file_sha256(target_path),
        "profile_name": profile_name,
        "g_definition": "target_pair_status=PAIRED and event_vs_online_changed=True; L_r>=K and d_t<K",
        "g_total_count": int(len(g)),
        "g_evaluable_count": int(len(paired_predictions)),
        "g_unique_evaluable_count": int(paired_predictions["sample_id"].nunique()),
        "g_evaluable_by_partition": {
            str(partition): int(count)
            for partition, count in paired_predictions.drop_duplicates(
                ["sample_id", "partition"]
            ).groupby("partition", dropna=False).size().items()
        },
        "future_used_for": "event target definition only",
        "future_forbidden_in_features": True,
        "model_retrained": True,
        "output_files": {
            "paired_predictions": str(paired_path),
            "metrics": str(metrics_path),
            "per_class_metrics": str(per_class_path),
            "transitions": str(transitions_path),
            "chart": str(chart_path),
        },
    }
    write_json(output_dir / "run_metadata.json", manifest)
    write_text(output_dir / "README.md", _build_readme(manifest))
    write_text(output_dir / "paired_event_online_report.md", _build_report(manifest, metrics, transitions))
    return EventOnlineComparisonResult(
        run_id=run_id,
        output_dir=output_dir,
        g_total_count=int(len(g)),
        g_evaluable_count=int(len(paired_predictions)),
        g_unique_evaluable_count=int(paired_predictions["sample_id"].nunique()),
        metric_row_count=int(len(metrics)),
    )


def _assert_prediction_contract(predictions: pd.DataFrame) -> None:
    required = {
        "model_key",
        "target_view_id",
        "feature_view_id",
        "fold_id",
        "partition",
        "sample_id",
        "label_name_true",
        "label_name_pred",
        "class_names_json",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Prediction artifact is missing paired-analysis columns: {sorted(missing)}")
    key = ["model_key", "target_view_id", "feature_view_id", "fold_id", "partition", "sample_id"]
    if predictions.duplicated(key, keep=False).any():
        raise ValueError("Prediction artifact has duplicate target/feature/sample rows.")


def _load_g_cohort(targets: pd.DataFrame) -> pd.DataFrame:
    required = {
        "sample_id",
        "target_view_id",
        "target_pair_status",
        "event_vs_online_changed",
        "event_label_name",
        "online_label_name",
        "support_depth_at_anchor",
        "eventual_run_length",
        "required_k",
        "run_id",
    }
    missing = required - set(targets.columns)
    if missing:
        raise ValueError(f"Target artifact is missing G-cohort columns: {sorted(missing)}")
    g = targets.loc[
        targets["target_view_id"].astype("string").eq(Y_EVENT)
        & targets["target_pair_status"].astype("string").eq("PAIRED")
        & targets["event_vs_online_changed"].fillna(False).astype(bool)
    ].copy()
    g["sample_id"] = g["sample_id"].astype("string")
    if g["sample_id"].duplicated(keep=False).any():
        raise ValueError("G cohort is not unique by sample_id.")
    if not g.empty and not (
        g["event_label_name"].astype("string").eq(
            "persistent_low_relative_moisture_at_anchor"
        ).all()
        and g["online_label_name"].astype("string").eq(
            "unresolved_environmental_evidence_at_anchor"
        ).all()
    ):
        raise ValueError("G cohort does not have the expected LOW(event)/UNRES(online) semantics.")
    if not g.empty and not (
        pd.to_numeric(g["eventual_run_length"], errors="coerce")
        >= pd.to_numeric(g["required_k"], errors="coerce")
    ).all():
        raise ValueError("G cohort contains a row with eventual run length below K.")
    if not g.empty and not (
        pd.to_numeric(g["support_depth_at_anchor"], errors="coerce")
        < pd.to_numeric(g["required_k"], errors="coerce")
    ).all():
        raise ValueError("G cohort contains a row with support depth at or above K.")
    return g.loc[
        :,
        [
            "sample_id",
            "run_id",
            "deployment_segment_id",
            "support_depth_at_anchor",
            "eventual_run_length",
            "required_k",
            "event_label_name",
            "online_label_name",
        ],
    ].convert_dtypes()


def _join_g_predictions(g: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    event = predictions.loc[predictions["target_view_id"].astype("string").eq(Y_EVENT)].copy()
    online = predictions.loc[predictions["target_view_id"].astype("string").eq(Y_ONLINE)].copy()
    join_keys = ["model_key", "feature_view_id", "fold_id", "partition", "sample_id"]
    event = event.rename(
        columns={
            "label_name_true": "event_model_label_true",
            "label_name_pred": "event_model_label_pred",
            "class_names_json": "event_class_names_json",
        }
    )
    online = online.rename(
        columns={
            "label_name_true": "online_model_label_true",
            "label_name_pred": "online_model_label_pred",
            "class_names_json": "online_class_names_json",
        }
    )
    event = event.loc[:, join_keys + ["event_model_label_true", "event_model_label_pred", "event_class_names_json"]]
    online = online.loc[:, join_keys + ["online_model_label_true", "online_model_label_pred", "online_class_names_json"]]
    joined = event.merge(online, on=join_keys, how="inner", validate="one_to_one")
    joined = joined.merge(g, on="sample_id", how="inner", validate="many_to_one")
    if joined.empty:
        return joined.convert_dtypes()
    expected = set(g["sample_id"].astype("string"))
    present = set(joined["sample_id"].astype("string"))
    joined["g_prediction_coverage"] = len(present) / len(expected) if expected else float("nan")
    return joined.sort_values(["feature_view_id", "partition", "sample_id"], kind="stable").reset_index(drop=True).convert_dtypes()


def _build_metrics(paired: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    if paired.empty:
        return pd.DataFrame().convert_dtypes(), pd.DataFrame().convert_dtypes()
    for keys, frame in paired.groupby(["model_key", "feature_view_id", "fold_id", "partition"], sort=False):
        model_key, feature_view_id, fold_id, partition = (str(value) for value in keys)
        for alignment, prediction_column, target_column, class_column in (
            (
                "event_model_vs_Y_event",
                "event_model_label_pred",
                "event_label_name",
                "event_class_names_json",
            ),
            (
                "online_model_vs_Y_online",
                "online_model_label_pred",
                "online_label_name",
                "online_class_names_json",
            ),
            (
                "event_model_vs_Y_online",
                "event_model_label_pred",
                "online_label_name",
                "event_class_names_json",
            ),
            (
                "online_model_vs_Y_event",
                "online_model_label_pred",
                "event_label_name",
                "online_class_names_json",
            ),
        ):
            class_names = json.loads(str(frame[class_column].dropna().iloc[0]))
            class_lookup = {name: index for index, name in enumerate(class_names)}
            y_true = frame[target_column].astype("string").map(class_lookup)
            y_pred = frame[prediction_column].astype("string").map(class_lookup)
            valid = y_true.notna() & y_pred.notna()
            metrics = summarize_protocol_classification(
                y_true.loc[valid].astype(int).to_numpy(),
                y_pred.loc[valid].astype(int).to_numpy(),
                class_names,
            )
            predictions_count = frame[prediction_column].astype("string").value_counts().to_dict()
            row = {
                "model_key": model_key,
                "feature_view_id": feature_view_id,
                "fold_id": fold_id,
                "partition": partition,
                "prediction_target_alignment": alignment,
                "g_row_count": int(valid.sum()),
                "accuracy": float(metrics["accuracy"]),
                "supported_class_balanced_accuracy": float(metrics["supported_class_balanced_accuracy"]),
                "supported_class_macro_f1": float(metrics["supported_class_macro_f1"]),
                "weighted_f1": float(metrics["weighted_f1"]),
                "pred_low_count": int(predictions_count.get("persistent_low_relative_moisture_at_anchor", 0)),
                "pred_unres_count": int(predictions_count.get("unresolved_environmental_evidence_at_anchor", 0)),
                "pred_ref_count": int(predictions_count.get("reference_context_at_anchor", 0)),
            }
            metric_rows.append(row)
            for class_name, class_metrics in metrics["class_metrics"].items():
                per_class_rows.append(
                    {
                        **{key: row[key] for key in row if key not in {"accuracy", "supported_class_balanced_accuracy", "supported_class_macro_f1", "weighted_f1"}},
                        "class_name": class_name,
                        "precision": class_metrics["precision"],
                        "recall": class_metrics["recall"],
                        "f1_score": class_metrics["f1_score"],
                        "support": class_metrics["support"],
                        "estimable": class_metrics["estimable"],
                    }
                )
    return pd.DataFrame(metric_rows).convert_dtypes(), pd.DataFrame(per_class_rows).convert_dtypes()


def _build_transitions(paired: pd.DataFrame) -> pd.DataFrame:
    if paired.empty:
        return pd.DataFrame().convert_dtypes()
    return (
        paired.groupby(
            ["model_key", "feature_view_id", "fold_id", "partition", "event_model_label_pred", "online_model_label_pred"],
            dropna=False,
        )
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["feature_view_id", "partition", "event_model_label_pred", "online_model_label_pred"], kind="stable")
        .convert_dtypes()
    )


def _write_accuracy_chart(metrics: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    aligned = metrics.loc[
        metrics["prediction_target_alignment"].isin(["event_model_vs_Y_event", "online_model_vs_Y_online"])
    ].copy()
    if aligned.empty:
        return
    key_pairs = [
        (str(row["feature_view_id"]), str(row["partition"]))
        for _, row in (
            aligned[["feature_view_id", "partition"]]
            .drop_duplicates()
            .sort_values(["feature_view_id", "partition"], kind="stable")
            .iterrows()
        )
    ]
    labels = [
        f"{feature.replace('v2_', '')}\n{partition}"
        for feature, partition in key_pairs
    ]
    x = list(range(len(labels)))
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    for offset, alignment, color, label in (
        (-width / 2, "event_model_vs_Y_event", "#4c78a8", "event model → Y_event"),
        (width / 2, "online_model_vs_Y_online", "#f58518", "online model → Y_online"),
    ):
        series = aligned.loc[aligned["prediction_target_alignment"].eq(alignment)].set_index(
            ["feature_view_id", "partition"]
        )["accuracy"]
        values = [float(series.get(key, float("nan"))) for key in key_pairs]
        ax.bar([value + offset for value in x], values, width=width, label=label, color=color)
        for position, metric in zip([value + offset for value in x], values, strict=True):
            if pd.notna(metric):
                ax.text(position, metric + 0.015, f"{metric:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_title("G cohort accuracy: model-facing semantics")
    ax.set_ylabel("Accuracy")
    ax.set_ylim(0, 1.08)
    ax.set_xticks(x, labels)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _build_readme(manifest: dict[str, object]) -> str:
    return f"""# Paired event/online comparison

This analysis uses the newly trained `{manifest['profile_name']}` model run.
It evaluates only the diagnostic G cohort: `{manifest['g_definition']}`.
`Y_event` is retrospective and is not deployable; future information is not a
feature.  See `paired_event_online_report.md` and `run_metadata.json`.
"""


def _build_report(manifest: dict[str, object], metrics: pd.DataFrame, transitions: pd.DataFrame) -> str:
    lines = [
        "# Paired event/online model comparison — report",
        "",
        "> Diagnostic benchmark on G; it does not replace the primary temporal benchmark.",
        "",
        "## Cohort",
        "",
        f"- G definition: `{manifest['g_definition']}`",
        f"- G rows in target artifact: `{manifest['g_total_count']}`",
        f"- G unique samples available in held-out predictions: `{manifest['g_unique_evaluable_count']}`",
        f"- Held-out prediction rows (2 feature views): `{manifest['g_evaluable_count']}`",
        f"- Held-out unique-sample coverage by partition: `{manifest['g_evaluable_by_partition']}`",
        "- Expected semantics on G: `Y_event=LOW`, `Y_online=UNRES`.",
        "",
        "## Metrics",
        "",
        _markdown_table(
            metrics,
            [
                "model_key",
                "feature_view_id",
                "partition",
                "prediction_target_alignment",
                "g_row_count",
                "accuracy",
                "supported_class_macro_f1",
                "supported_class_balanced_accuracy",
                "pred_low_count",
                "pred_unres_count",
                "pred_ref_count",
            ],
        ),
        "",
        "## Prediction transitions",
        "",
        _markdown_table(
            transitions,
            [
                "model_key",
                "feature_view_id",
                "partition",
                "event_model_label_pred",
                "online_model_label_pred",
                "row_count",
            ],
        ),
        "",
        "The aligned rows are the direct test of whether each model learns its declared target semantics. Cross-aligned rows are diagnostic only.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: f"{float(value):.6f}")
        else:
            display[column] = display[column].astype("string").fillna("")
    headers = display.columns.tolist()
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    rows.extend("| " + " | ".join(str(value) for value in row) + " |" for row in display.itertuples(index=False, name=None))
    return "\n".join(rows)
