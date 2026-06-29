from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Wedge
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import BENCHMARK_DATASETS_ROOT, BENCHMARK_ROOT
from Backend.Benchmark.common.raw_tabular_dataset import build_raw_tabular_source_registry
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json
from Backend.Benchmark.shared.labels import build_label_frame
from Backend.Benchmark.tabular_benchmark.src.config.settings import (
    default_dataset_output_root,
    default_training_output_root,
)

LABEL_MODES = ("binary", "tri_class", "four_class")
FOCUS_EXPERIMENTS = ("v1", "v2", "v3")
SECTION55_EXPERIMENTS = ("v1", "v2")
ALL_EXPERIMENTS = ("v0", "v1", "v2", "v3", "v4", "v5")
MATRIX_EXPERIMENTS = ("v0", "v1", "v2", "v3")
METRIC_EXPERIMENTS = ("v0", "v1", "v2", "v3")
SECTION57_EXPERIMENTS = ("v1", "v2")
REPORT_SNAPSHOT_LABEL_COUNTS: dict[str, list[tuple[str, int]]] = {
    "big_label": [
        ("none", 3148),
        ("stress_context", 112),
        ("system_timing", 49),
        ("weather_context", 26),
        ("sensor_fault_anomaly", 19),
        ("intervention_context", 12),
    ],
    "binary": [
        ("normal_context", 3148),
        ("non_normal_context", 218),
    ],
    "tri_class": [
        ("normal", 3148),
        ("system_context", 80),
        ("field_context", 138),
    ],
    "four_class": [
        ("normal_context", 3148),
        ("water_deficit", 112),
        ("packet_loss_outage", 68),
        ("rain_or_fertigation_context", 38),
    ],
}
MODEL_SHORT_NAMES = {
    "xgboost": "XGB",
    "tabnet_classifier": "TabNet",
    "ft_transformer_classifier": "FTT",
}
THESIS_COLORS = {
    "green": "#2d6a4f",
    "green_soft": "#d8f3dc",
    "amber": "#d6a33b",
    "blue": "#4d95bf",
    "blue_dark": "#1d4ed8",
    "slate": "#64748b",
    "slate_soft": "#e2e8f0",
    "red": "#dc2626",
    "ink": "#0f172a",
    "grid": "#d9e2ec",
    "canvas": "#fbfcfa",
}
FOCUS_VERSION_COLORS = {
    "v0": "#cbd5e1",
    "v1": THESIS_COLORS["green"],
    "v2": THESIS_COLORS["amber"],
    "v3": THESIS_COLORS["blue"],
    "v4": "#cbd5e1",
    "v5": "#cbd5e1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Chapter 5 visual report pack from benchmark artifacts.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(BENCHMARK_ROOT / "reporting" / "artifacts" / "chapter5_visual_reports").resolve(),
        help="Output root for generated chapter 5 visual packs.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_build_run(label_mode: str) -> Path:
    root = default_dataset_output_root(label_mode)
    if not root.exists():
        raise FileNotFoundError(f"Dataset build root not found: {root}")
    candidates = [path.parent for path in root.rglob("dataset_manifest.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No dataset manifests found under: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _find_latest_training_run(label_mode: str) -> Path:
    root = default_training_output_root(label_mode)
    if not root.exists():
        raise FileNotFoundError(f"Training root not found: {root}")
    candidates = [path.parent for path in root.rglob("training_report.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No training runs found under: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _find_dataset_report(dataset_root: Path, suffix: str) -> Path:
    matches = sorted(dataset_root.glob(f"*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"Could not find dataset report '*{suffix}' under {dataset_root}")
    return matches[-1]


def _resolve_payload_path(raw_path: object, *, fallback_root: Path) -> Path:
    candidate = Path(str(raw_path)).resolve()
    if candidate.exists():
        return candidate
    fallback = (fallback_root / candidate.name).resolve()
    if fallback.exists():
        return fallback
    return candidate


def _friendly_label_mode(label_mode: str) -> str:
    mapping = {"binary": "Nhị phân", "tri_class": "Tam phân", "four_class": "Tứ phân"}
    return mapping.get(label_mode, label_mode)


def _friendly_branch_name(branch_name: str) -> str:
    mapping = {
        "big_label": "big_label",
        "binary": "Nhị phân",
        "tri_class": "Tam phân",
        "four_class": "Tứ phân",
    }
    return mapping.get(branch_name, branch_name)


def _format_int(value: float | int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _wrap_tick_labels(labels: list[str], *, max_width: int = 18) -> list[str]:
    wrapped: list[str] = []
    for label in labels:
        tokens = str(label).replace("_", "_ ").split()
        lines: list[str] = []
        current = ""
        for token in tokens:
            candidate = token if not current else f"{current} {token}"
            if len(candidate) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = token
        if current:
            lines.append(current)
        wrapped.append("\n".join(lines).replace("_ ", "_"))
    return wrapped


def _apply_word_chart_style(ax: plt.Axes, *, y_grid: bool = True, x_grid: bool = False) -> None:
    ax.set_facecolor("#ffffff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(THESIS_COLORS["slate_soft"])
    ax.spines["bottom"].set_color(THESIS_COLORS["slate_soft"])
    ax.tick_params(labelsize=11, colors=THESIS_COLORS["ink"])
    if y_grid:
        ax.grid(axis="y", color=THESIS_COLORS["grid"], alpha=0.7, linewidth=0.9)
    if x_grid:
        ax.grid(axis="x", color=THESIS_COLORS["grid"], alpha=0.7, linewidth=0.9)
    ax.set_axisbelow(True)


def _display_class_name(*, label_mode: str, class_name: str) -> str:
    if label_mode == "binary":
        if class_name == "normal":
            return "normal_context"
        if class_name == "abnormal":
            return "non_normal_context"
    return class_name


def _feature_group_flags(feature_columns: list[str], source_csv_names: tuple[str, ...]) -> dict[str, int]:
    feature_set = set(feature_columns)
    return {
        "raw_core": int(any(name in feature_set for name in ("soil_temp", "soil_humidity", "air_temp", "air_humidity", "EC"))),
        "chemistry_npk": int(any(name in feature_set for name in ("pH", "N", "P", "K"))),
        "delta_1step": int(any(name.endswith("_delta_1step") for name in feature_set)),
        "window_3h": int(any("_3h" in name for name in feature_set)),
        "window_8h": int(any("_8h" in name for name in feature_set)),
        "window_24h": int(any("_24h" in name for name in feature_set)),
        "humidity_saturation": int(any("saturation" in name for name in feature_set)),
        "multi_source_union": int(len(source_csv_names) > 1),
    }


def build_visual_pack(output_root: Path) -> dict[str, object]:
    output_root = output_root.resolve()
    run_id, output_dir = create_run_directory(output_root, prefix="chapter5_visual")

    dataset_root = BENCHMARK_DATASETS_ROOT.resolve()
    dataset_build_report_path = _find_dataset_report(dataset_root, "dataset_build_report.json")
    labeling_report_path = _find_dataset_report(dataset_root, "real_event_labeling_report.json")
    alignment_manifest_path = dataset_root / "manifest.json"

    dataset_build_report = _load_json(dataset_build_report_path)
    labeling_report = _load_json(labeling_report_path)
    alignment_manifest = _load_json(alignment_manifest_path)

    dataset_runs = {label_mode: _find_latest_build_run(label_mode) for label_mode in LABEL_MODES}
    training_runs = {label_mode: _find_latest_training_run(label_mode) for label_mode in LABEL_MODES}
    dataset_manifests = {
        label_mode: _load_json(dataset_runs[label_mode] / "dataset_manifest.json") for label_mode in LABEL_MODES
    }

    labeled_csv_path = _resolve_payload_path(labeling_report["output_csv"], fallback_root=dataset_root)
    labeled_frame = build_label_frame(pd.read_csv(labeled_csv_path))

    section53 = _build_section53(output_dir=output_dir, alignment_manifest=alignment_manifest, labeling_report=labeling_report, dataset_manifests=dataset_manifests)
    section54 = _build_section54(output_dir=output_dir, labeled_frame=labeled_frame)
    section55 = _build_section55(output_dir=output_dir, dataset_runs=dataset_runs)
    section57 = _build_section57(output_dir=output_dir, training_runs=training_runs)

    summary_path = output_dir / "chapter5_visual_summary.md"
    summary_path.write_text(
        _build_markdown_summary(
            dataset_root=dataset_root,
            dataset_build_report_path=dataset_build_report_path,
            labeling_report_path=labeling_report_path,
            section53=section53,
            section54=section54,
            section55=section55,
            section57=section57,
        ),
        encoding="utf-8",
    )

    write_json(
        output_dir / "manifest.json",
        {
            "run_id": run_id,
            "output_dir": str(output_dir),
            "dataset_build_report_path": str(dataset_build_report_path),
            "labeling_report_path": str(labeling_report_path),
            "dataset_runs": {key: str(value) for key, value in dataset_runs.items()},
            "training_runs": {key: str(value) for key, value in training_runs.items()},
            "generated_files": sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()),
        },
    )
    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "summary_path": str(summary_path),
    }


def _build_section53(
    *,
    output_dir: Path,
    alignment_manifest: dict[str, object],
    labeling_report: dict[str, object],
    dataset_manifests: dict[str, dict[str, object]],
) -> dict[str, object]:
    section_dir = output_dir / "5_3_pipeline_counts"
    section_dir.mkdir(parents=True, exist_ok=True)

    raw_counts = pd.DataFrame(
        [
            {"stage": "Firebase raw - NPK", "row_count": int(alignment_manifest["input_counts"]["npk_records"])},
            {"stage": "Firebase raw - SHT30", "row_count": int(alignment_manifest["input_counts"]["sht30_records"])},
            {"stage": "Firebase raw - METEO", "row_count": int(alignment_manifest["input_counts"]["meteo_records"])},
            {"stage": "Alignment anchor timestamps", "row_count": int(alignment_manifest["input_counts"]["anchor_count"])},
        ]
    )
    raw_counts.to_csv(section_dir / "raw_source_counts.csv", index=False)
    _render_horizontal_bar(
        raw_counts,
        category_column="stage",
        value_column="row_count",
        title="Hình 5.3a. Số bản ghi dữ liệu thực theo nguồn cảm biến",
        output_path=section_dir / "chart_raw_source_counts.png",
        color=THESIS_COLORS["green"],
    )

    processed_rows = [
        {"stage": "Aligned rows", "row_count": int(alignment_manifest["row_count"])},
        {"stage": "Labeled rows", "row_count": int(labeling_report["row_count"])},
    ]
    for label_mode in LABEL_MODES:
        manifest = dataset_manifests[label_mode]
        v1_report = next(item for item in manifest["experiment_reports"] if item["experiment_name"] == "v1")
        processed_rows.append(
            {
                "stage": f"Prepared rows ({label_mode}, v1)",
                "row_count": int(v1_report["row_count"]),
            }
        )
    processed_df = pd.DataFrame(processed_rows)
    processed_df["rows_removed_vs_labeled"] = int(labeling_report["row_count"]) - processed_df["row_count"]
    processed_df.to_csv(section_dir / "processed_stage_rows.csv", index=False)
    _render_vertical_bar(
        processed_df,
        category_column="stage",
        value_column="row_count",
        title="Hình 5.3b. Số dòng qua các giai đoạn xử lý dữ liệu",
        output_path=section_dir / "chart_processed_stage_rows.png",
        color=THESIS_COLORS["green"],
    )

    normal_count = int(labeling_report["big_label_counts"].get("none", 0))
    non_normal_count = int(labeling_report["row_count"]) - normal_count
    binary_total = normal_count + non_normal_count
    binary_ratio = (non_normal_count / binary_total) if binary_total else 0.0
    overview_rows = [
        {"group": "firebase_raw", "item": "npk_records", "row_count": int(alignment_manifest["input_counts"]["npk_records"]), "ratio": np.nan, "notes": "Firebase raw telemetry - NPK"},
        {"group": "firebase_raw", "item": "sht30_records", "row_count": int(alignment_manifest["input_counts"]["sht30_records"]), "ratio": np.nan, "notes": "Firebase raw telemetry - SHT30"},
        {"group": "firebase_raw", "item": "meteo_records", "row_count": int(alignment_manifest["input_counts"]["meteo_records"]), "ratio": np.nan, "notes": "Firebase raw telemetry - METEO"},
        {"group": "stage", "item": "alignment_anchor_timestamps", "row_count": int(alignment_manifest["input_counts"]["anchor_count"]), "ratio": np.nan, "notes": "Anchor timestamps retained after alignment"},
        {"group": "stage", "item": "benchmark_input_aligned_csv", "row_count": int(alignment_manifest["row_count"]), "ratio": np.nan, "notes": "Rows exported to benchmark_input_aligned.csv"},
        {"group": "stage", "item": "benchmark_input_labeled_csv", "row_count": int(labeling_report["row_count"]), "ratio": np.nan, "notes": "Rows exported to benchmark_input_labeled.csv"},
        {"group": "binary_collapse", "item": "normal_context", "row_count": normal_count, "ratio": (normal_count / binary_total) if binary_total else 0.0, "notes": "Binary benchmark collapse - normal_context"},
        {"group": "binary_collapse", "item": "non_normal_context", "row_count": non_normal_count, "ratio": binary_ratio, "notes": "Binary benchmark collapse - non_normal_context"},
    ]
    overview_df = pd.DataFrame(overview_rows)
    overview_df.to_csv(section_dir / "pipeline_overview_counts.csv", index=False)
    _render_pipeline_overview_infographic(
        raw_counts=raw_counts,
        aligned_rows=int(alignment_manifest["row_count"]),
        labeled_rows=int(labeling_report["row_count"]),
        normal_count=normal_count,
        non_normal_count=non_normal_count,
        output_path=section_dir / "chart_pipeline_overview_infographic.png",
    )

    prepared_rows: list[dict[str, object]] = []
    for label_mode, manifest in dataset_manifests.items():
        for item in manifest["experiment_reports"]:
            prepared_rows.append(
                {
                    "label_mode": label_mode,
                    "experiment_name": item["experiment_name"],
                    "row_count": int(item["row_count"]),
                    "dropped_vs_labeled": int(labeling_report["row_count"]) - int(item["row_count"]),
                }
            )
    prepared_rows_df = pd.DataFrame(prepared_rows)
    prepared_rows_df.to_csv(section_dir / "prepared_rows_all_versions.csv", index=False)
    prepared_heatmap = prepared_rows_df.pivot(index="label_mode", columns="experiment_name", values="row_count").reindex(index=LABEL_MODES, columns=MATRIX_EXPERIMENTS)
    _render_heatmap(
        prepared_heatmap.to_numpy(dtype=float),
        row_labels=[_friendly_label_mode(name) for name in prepared_heatmap.index.tolist()],
        col_labels=[name.upper() for name in prepared_heatmap.columns.tolist()],
        title="Hình 5.3c. Số dòng prepared dataset theo nhánh nhãn và version (v0-v3)",
        output_path=section_dir / "chart_prepared_rows_heatmap.png",
        value_format="int",
        cmap_name="Greens",
    )
    return {"section_dir": str(section_dir)}


def _build_section54(*, output_dir: Path, labeled_frame: pd.DataFrame) -> dict[str, object]:
    section_dir = output_dir / "5_4_label_distributions"
    section_dir.mkdir(parents=True, exist_ok=True)

    counts_map = {
        branch_name: pd.Series({label_name: count for label_name, count in rows}, dtype="int64")
        for branch_name, rows in REPORT_SNAPSHOT_LABEL_COUNTS.items()
    }
    rows: list[dict[str, object]] = []
    for branch_name, counts in counts_map.items():
        total = int(counts.sum())
        for label_name, count in counts.items():
            rows.append(
                {
                    "branch_name": branch_name,
                    "label_name": str(label_name),
                    "row_count": int(count),
                    "ratio": float(count / total) if total else 0.0,
                }
            )
    distribution_df = pd.DataFrame(rows)
    distribution_df.to_csv(section_dir / "label_distribution_counts.csv", index=False)
    _render_label_distribution_panels(
        counts_map=counts_map,
        output_path=section_dir / "chart_label_distribution_panels.png",
    )
    return {"section_dir": str(section_dir)}


def _build_section55(*, output_dir: Path, dataset_runs: dict[str, Path]) -> dict[str, object]:
    section_dir = output_dir / "5_5_split_results"
    section_dir.mkdir(parents=True, exist_ok=True)

    split_rows: list[dict[str, object]] = []
    support_rows: list[dict[str, object]] = []
    for label_mode, run_dir in dataset_runs.items():
        for experiment_name in SECTION55_EXPERIMENTS:
            summary = _load_json(run_dir / "experiments" / experiment_name / "split_label_summary.json")
            for split_name, payload in summary.items():
                row_count = int(payload["row_count"])
                split_rows.append(
                    {
                        "label_mode": label_mode,
                        "experiment_name": experiment_name,
                        "split_name": split_name,
                        "row_count": row_count,
                    }
                )
                for class_name, count in payload["selected_label_counts"].items():
                    support_rows.append(
                        {
                            "label_mode": label_mode,
                            "experiment_name": experiment_name,
                            "split_name": split_name,
                            "class_name": str(class_name),
                            "class_name_display": _display_class_name(label_mode=label_mode, class_name=str(class_name)),
                            "class_count": int(count),
                        }
                    )

    split_df = pd.DataFrame(split_rows)
    support_df = pd.DataFrame(support_rows)
    split_df.to_csv(section_dir / "split_counts_focus_versions.csv", index=False)
    support_df.to_csv(section_dir / "split_class_support_focus_versions.csv", index=False)

    _render_split_stacked_panels(
        split_df=split_df,
        output_path=section_dir / "chart_split_counts_focus_versions.png",
    )

    excluded_gap_df = split_df[split_df["split_name"] == "excluded_gap"].copy()
    _render_grouped_bar(
        frame=excluded_gap_df,
        category_column="experiment_name",
        series_column="label_mode",
        value_column="row_count",
        title="Section 5.5 - Excluded-gap rows by version and label branch",
        output_path=section_dir / "chart_excluded_gap_focus_versions.png",
        category_order=list(SECTION55_EXPERIMENTS),
        series_order=list(LABEL_MODES),
        series_colors=["#2d6a4f", "#d6a33b", "#4d95bf"],
        y_label="row_count",
    )

    heatmap_frame = (
        support_df[support_df["split_name"].isin(["validation", "test"])]
        .assign(column_key=lambda frame: frame["experiment_name"] + " | " + frame["split_name"])
        .assign(row_key=lambda frame: frame["label_mode"] + " | " + frame["class_name_display"])
        .pivot(index="row_key", columns="column_key", values="class_count")
        .fillna(0)
    )
    ordered_columns = [f"{experiment} | validation" for experiment in SECTION55_EXPERIMENTS] + [f"{experiment} | test" for experiment in SECTION55_EXPERIMENTS]
    heatmap_frame = heatmap_frame.reindex(columns=ordered_columns).fillna(0)
    row_order = []
    for label_mode in LABEL_MODES:
        subset = support_df[support_df["label_mode"] == label_mode]["class_name_display"].drop_duplicates().tolist()
        row_order.extend([f"{label_mode} | {class_name}" for class_name in subset])
    heatmap_frame = heatmap_frame.reindex(row_order).fillna(0)
    _render_heatmap(
        heatmap_frame.to_numpy(dtype=float),
        row_labels=[value.replace(" | ", " / ") for value in heatmap_frame.index.tolist()],
        col_labels=[value.replace(" | ", "\n") for value in heatmap_frame.columns.tolist()],
        title="Hình 5.5c. Độ phủ lớp trong validation và test",
        output_path=section_dir / "chart_validation_test_class_support.png",
        value_format="int",
        cmap_name="Blues",
    )
    return {"section_dir": str(section_dir)}


def _build_section57(*, output_dir: Path, training_runs: dict[str, Path]) -> dict[str, object]:
    section_dir = output_dir / "5_7_feature_source_analysis"
    section_dir.mkdir(parents=True, exist_ok=True)

    registry = build_raw_tabular_source_registry()
    registry_rows: list[dict[str, object]] = []
    for version_name in ALL_EXPERIMENTS:
        spec = registry[version_name]
        feature_groups = _feature_group_flags(list(spec.feature_columns), spec.source_csv_names)
        registry_rows.append(
            {
                "version": version_name,
                "description": spec.description,
                "source_csv_names": ", ".join(spec.source_csv_names),
                "feature_count": len(spec.feature_columns),
                "chapter5_status": "focus" if version_name in FOCUS_EXPERIMENTS else "historical_ablation",
                **feature_groups,
            }
        )
    registry_df = pd.DataFrame(registry_rows)
    registry_df.to_csv(section_dir / "feature_source_registry.csv", index=False)

    matrix_columns = [
        "raw_core",
        "chemistry_npk",
        "delta_1step",
        "window_3h",
        "window_8h",
        "window_24h",
        "humidity_saturation",
        "multi_source_union",
    ]
    matrix_df = registry_df.set_index("version")[matrix_columns].reindex(SECTION57_EXPERIMENTS)
    _render_heatmap(
        matrix_df.to_numpy(dtype=float),
        row_labels=[name.upper() for name in matrix_df.index.tolist()],
        col_labels=["raw", "chem", "d1", "3h", "8h", "24h", "sat", "union"],
        title="Hình 5.7a. Ma trận thành phần đặc trưng của các version v1-v2",
        output_path=section_dir / "chart_feature_source_matrix.png",
        value_format="binary",
        cmap_name="Greens",
    )

    metric_rows: list[dict[str, object]] = []
    for label_mode, run_dir in training_runs.items():
        metrics = pd.read_csv(run_dir / "aggregate_model_metrics.csv")
        for experiment_name in ALL_EXPERIMENTS:
            panel = metrics[metrics["experiment_name"].astype(str) == experiment_name].copy()
            if panel.empty:
                continue
            selected = panel.sort_values(["validation_macro_f1", "test_macro_f1"], ascending=False).iloc[0]
            metric_rows.append(
                {
                    "label_mode": label_mode,
                    "experiment_name": experiment_name,
                    "selected_model_name": str(selected["model_name"]),
                    "validation_macro_f1": float(selected["validation_macro_f1"]),
                    "test_macro_f1": float(selected["test_macro_f1"]),
                    "test_balanced_accuracy": float(selected["test_balanced_accuracy"]),
                }
            )
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(section_dir / "best_validation_selected_metrics_all_versions.csv", index=False)
    metrics_plot_df = metrics_df[metrics_df["experiment_name"].astype(str).isin(SECTION57_EXPERIMENTS)].copy()

    _render_metric_panels(
        metrics_df=metrics_plot_df,
        metric_column="test_macro_f1",
        title="Hình 5.7b. Test macro-F1 tốt nhất tại mỗi version dữ liệu thực (v1-v2)",
        output_path=section_dir / "chart_test_macro_f1_v0_to_v3.png",
    )
    _render_metric_panels(
        metrics_df=metrics_plot_df,
        metric_column="test_balanced_accuracy",
        title="Hình 5.7c. Test balanced accuracy tốt nhất tại mỗi version dữ liệu thực (v1-v2)",
        output_path=section_dir / "chart_test_balanced_accuracy_v0_to_v3.png",
    )
    return {"section_dir": str(section_dir)}


def _render_horizontal_bar(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_column: str,
    title: str,
    output_path: Path,
    color: str,
) -> None:
    plot_df = frame.sort_values(value_column, ascending=True).copy()
    labels = _wrap_tick_labels(plot_df[category_column].astype(str).tolist(), max_width=22)
    fig, ax = plt.subplots(figsize=(11.5, 6.5), facecolor=THESIS_COLORS["canvas"])
    bars = ax.barh(labels, plot_df[value_column], color=color, alpha=0.92, height=0.62)
    for bar, value in zip(bars, plot_df[value_column].tolist(), strict=False):
        ax.text(value + max(plot_df[value_column].max() * 0.012, 3.0), bar.get_y() + bar.get_height() / 2.0, _format_int(value), va="center", fontsize=11, color=THESIS_COLORS["ink"])
    ax.set_title(title, fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"], pad=12)
    ax.set_xlabel("Số bản ghi", fontsize=12, color=THESIS_COLORS["ink"])
    _apply_word_chart_style(ax, y_grid=False, x_grid=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_vertical_bar(
    frame: pd.DataFrame,
    *,
    category_column: str,
    value_column: str,
    title: str,
    output_path: Path,
    color: str,
) -> None:
    plot_df = frame.copy()
    labels = _wrap_tick_labels(plot_df[category_column].astype(str).tolist(), max_width=16)
    fig, ax = plt.subplots(figsize=(12, 6.6), facecolor=THESIS_COLORS["canvas"])
    bars = ax.bar(labels, plot_df[value_column], color=color, alpha=0.92, width=0.62)
    for bar, value in zip(bars, plot_df[value_column].tolist(), strict=False):
        ax.text(bar.get_x() + bar.get_width() / 2.0, value + max(plot_df[value_column].max() * 0.01, 3.0), _format_int(value), ha="center", va="bottom", fontsize=10.5, color=THESIS_COLORS["ink"])
    ax.set_title(title, fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"], pad=12)
    ax.set_ylabel("Số dòng", fontsize=12, color=THESIS_COLORS["ink"])
    _apply_word_chart_style(ax, y_grid=True, x_grid=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_heatmap(
    matrix: np.ndarray,
    *,
    row_labels: list[str],
    col_labels: list[str],
    title: str,
    output_path: Path,
    value_format: str,
    cmap_name: str,
) -> None:
    if matrix.size == 0:
        return
    fig, ax = plt.subplots(
        figsize=(max(8.5, 1.45 * len(col_labels)), max(5.3, 0.62 * len(row_labels) + 2.1)),
        facecolor=THESIS_COLORS["canvas"],
    )
    cmap = plt.get_cmap(cmap_name)
    vmax = 1.0 if value_format in {"float", "binary"} else float(np.nanmax(matrix))
    image = ax.imshow(matrix, cmap=cmap, vmin=0.0, vmax=max(vmax, 1.0 if value_format == "binary" else vmax))
    ax.set_xticks(range(len(col_labels)), _wrap_tick_labels(col_labels, max_width=12), rotation=0, ha="center")
    ax.set_yticks(range(len(row_labels)), _wrap_tick_labels(row_labels, max_width=22))
    ax.set_title(title, fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"], pad=14)
    for row_index in range(matrix.shape[0]):
        for col_index in range(matrix.shape[1]):
            value = matrix[row_index, col_index]
            if value_format == "int":
                text = _format_int(value)
            elif value_format == "binary":
                text = "Y" if int(value) > 0 else ""
            else:
                text = f"{value:.2f}"
            text_color = "#f8fafc" if value >= (0.55 * max(vmax, 1.0)) else THESIS_COLORS["ink"]
            ax.text(col_index, row_index, text, ha="center", va="center", fontsize=10, fontweight="bold", color=text_color)
    ax.set_xticks(np.arange(-0.5, len(col_labels), 1.0), minor=True)
    ax.set_yticks(np.arange(-0.5, len(row_labels), 1.0), minor=True)
    ax.grid(which="minor", color=THESIS_COLORS["grid"], linestyle="-", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.tick_params(labelsize=11, colors=THESIS_COLORS["ink"])
    fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_label_distribution_panels(*, counts_map: dict[str, pd.Series], output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 11.5), facecolor=THESIS_COLORS["canvas"])
    axes_list = axes.flatten()
    colors = {
        "big_label": THESIS_COLORS["green"],
        "binary": THESIS_COLORS["green"],
        "tri_class": THESIS_COLORS["amber"],
        "four_class": THESIS_COLORS["blue"],
    }
    for axis, (branch_name, counts) in zip(axes_list, counts_map.items(), strict=False):
        plot_counts = counts.sort_values(ascending=True)
        labels = _wrap_tick_labels(plot_counts.index.astype(str).tolist(), max_width=22)
        bars = axis.barh(labels, plot_counts.values.tolist(), color=colors.get(branch_name, THESIS_COLORS["slate"]), height=0.62)
        total = int(plot_counts.sum())
        for bar, value in zip(bars, plot_counts.values.tolist(), strict=False):
            ratio = (value / total) if total else 0.0
            axis.text(value + max(plot_counts.max() * 0.012, 1.0), bar.get_y() + bar.get_height() / 2.0, f"{_format_int(value)} ({ratio:.1%})", va="center", fontsize=10, color=THESIS_COLORS["ink"])
        axis.set_title(_friendly_branch_name(branch_name), fontsize=14, fontweight="bold", color=THESIS_COLORS["ink"])
        axis.set_xlabel("Số dòng", fontsize=11, color=THESIS_COLORS["ink"])
        _apply_word_chart_style(axis, y_grid=False, x_grid=True)
    fig.suptitle("Hình 5.4. Phân bố nhãn theo snapshot báo cáo 01/04/2026-10/05/2026", fontsize=17, fontweight="bold", color=THESIS_COLORS["ink"])
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_pipeline_overview_infographic(
    *,
    raw_counts: pd.DataFrame,
    aligned_rows: int,
    labeled_rows: int,
    normal_count: int,
    non_normal_count: int,
    output_path: Path,
) -> None:
    total_binary = normal_count + non_normal_count
    non_normal_ratio = (non_normal_count / total_binary) if total_binary else 0.0
    normal_ratio = (normal_count / total_binary) if total_binary else 0.0
    raw_lookup = {str(row["stage"]): int(row["row_count"]) for _, row in raw_counts.iterrows()}

    fig = plt.figure(figsize=(16, 9), facecolor="#f8fbf7")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    frame = FancyBboxPatch(
        (0.03, 0.22),
        0.94,
        0.68,
        boxstyle="round,pad=0.018,rounding_size=0.02",
        facecolor="#ffffff",
        edgecolor="#2f855a",
        linewidth=2.0,
    )
    ax.add_patch(frame)

    banner = FancyBboxPatch(
        (0.315, 0.87),
        0.31,
        0.08,
        boxstyle="round,pad=0.01,rounding_size=0.02",
        facecolor="#2f855a",
        edgecolor="#2f855a",
        linewidth=0.0,
    )
    ax.add_patch(banner)
    ax.text(0.47, 0.91, "TỔNG QUAN DỮ LIỆU BENCHMARK", ha="center", va="center", fontsize=21, fontweight="bold", color="#f8fafc")

    card_lefts = [0.06, 0.285, 0.51, 0.735]
    card_width = 0.18
    card_bottom = 0.34
    card_height = 0.46
    card_colors = ["#1d4ed8", "#1d4ed8", "#2f855a", "#c2410c"]
    for card_left, color in zip(card_lefts, card_colors, strict=False):
        card = FancyBboxPatch(
            (card_left, card_bottom),
            card_width,
            card_height,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            facecolor="#ffffff",
            edgecolor="#d9e2ec",
            linewidth=1.0,
        )
        ax.add_patch(card)
        ax.add_patch(
            FancyBboxPatch(
                (card_left + 0.012, card_bottom + card_height - 0.018),
                card_width - 0.024,
                0.008,
                boxstyle="round,pad=0.0,rounding_size=0.004",
                facecolor=color,
                edgecolor=color,
                linewidth=0.0,
            )
        )

    ax.text(0.15, 0.70, "3 nguồn cảm biến", ha="center", va="center", fontsize=23, fontweight="bold", color="#1d4ed8")
    ax.text(0.15, 0.61, "Firebase raw\ntelemetry", ha="center", va="center", fontsize=20, fontweight="bold", color="#1d4ed8")
    ax.text(0.15, 0.49, f"NPK {raw_lookup.get('Firebase raw - NPK', 0)}", ha="center", va="center", fontsize=17, color="#0f172a")
    ax.text(0.15, 0.43, f"SHT30 {raw_lookup.get('Firebase raw - SHT30', 0)}", ha="center", va="center", fontsize=17, color="#0f172a")
    ax.text(0.15, 0.37, f"METEO {raw_lookup.get('Firebase raw - METEO', 0)}", ha="center", va="center", fontsize=17, color="#0f172a")
    ax.text(0.15, 0.29, "Bản ghi thô được kéo về\nở tầng Layer0", ha="center", va="center", fontsize=13.2, color="#475569")

    ax.text(0.375, 0.70, f"{aligned_rows}", ha="center", va="center", fontsize=38, fontweight="bold", color="#1d4ed8")
    ax.text(0.375, 0.61, "benchmark_input_\naligned.csv", ha="center", va="center", fontsize=20, fontweight="bold", color="#1d4ed8")
    ax.text(0.375, 0.48, f"Anchor timestamps:\n{_format_int(aligned_rows)}", ha="center", va="center", fontsize=17, color="#0f172a")
    ax.text(0.375, 0.38, "Số dòng giữ lại sau\ncăn chỉnh Layer1", ha="center", va="center", fontsize=15, color="#0f172a")
    ax.text(0.375, 0.29, "Bộ dòng lõi trước bước\ngán nhãn sự kiện", ha="center", va="center", fontsize=13.2, color="#475569")

    ax.text(0.60, 0.70, f"{labeled_rows}", ha="center", va="center", fontsize=38, fontweight="bold", color="#2f855a")
    ax.text(0.60, 0.61, "benchmark_input_\nlabeled.csv", ha="center", va="center", fontsize=20, fontweight="bold", color="#2f855a")
    ax.text(0.60, 0.48, "Số dòng sau bước gán nhãn\nsự kiện và bối cảnh", ha="center", va="center", fontsize=16.5, color="#0f172a")
    ax.text(0.60, 0.38, "Nguồn nhãn big_label cho\ncác nhánh benchmark downstream", ha="center", va="center", fontsize=14.2, color="#0f172a")
    ax.text(0.60, 0.29, "Không có dòng nào bị loại giữa\naligned và labeled", ha="center", va="center", fontsize=13.2, color="#475569")

    donut_center = (0.825, 0.575)
    donut_radius = 0.09
    donut_width = 0.045
    ax.add_patch(Wedge(donut_center, donut_radius, 0, 360, width=donut_width, facecolor="#d9f99d", edgecolor="#d9f99d"))
    ax.add_patch(Wedge(donut_center, donut_radius, 90, 90 - 360 * non_normal_ratio, width=donut_width, facecolor="#dc2626", edgecolor="#ffffff", linewidth=2.0))
    ax.text(0.825, 0.68, "Nhánh nhị phân", ha="center", va="center", fontsize=19, fontweight="bold", color="#c2410c")
    ax.text(0.825, 0.56, f"{non_normal_ratio:.2%}", ha="center", va="center", fontsize=24, fontweight="bold", color="#dc2626")
    ax.text(0.825, 0.46, "non_normal_context", ha="center", va="center", fontsize=16, color="#0f172a")
    ax.text(0.825, 0.29, "Đọc mất cân bằng này bằng\nmacro-F1 và confusion matrix", ha="center", va="center", fontsize=12.8, color="#475569")

    divider_y = 0.29
    ax.plot([0.06, 0.94], [divider_y, divider_y], color="#cbd5e1", linewidth=1.5, linestyle=(0, (4, 3)))
    ax.text(0.105, 0.252, "Phân bố nhãn sau collapse", ha="left", va="center", fontsize=18, fontweight="bold", color="#dc2626")
    ax.text(0.29, 0.215, f"{_format_int(normal_count)} normal_context ({normal_ratio:.2%})", ha="left", va="center", fontsize=17, fontweight="bold", color="#2f855a")
    ax.text(0.63, 0.215, f"{_format_int(non_normal_count)} non_normal_context ({non_normal_ratio:.2%})", ha="left", va="center", fontsize=17, fontweight="bold", color="#dc2626")

    note = FancyBboxPatch(
        (0.18, 0.04),
        0.64,
        0.10,
        boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor="#fff8e1",
        edgecolor="#f4b942",
        linewidth=1.5,
    )
    ax.add_patch(note)
    ax.text(0.50, 0.095, f"Chỉ {non_normal_ratio:.2%} số dòng thuộc lớp non_normal_context trong nhánh nhị phân.", ha="center", va="center", fontsize=15.2, fontweight="bold", color="#7c2d12")
    ax.text(0.50, 0.062, "Cần ưu tiên macro-F1, balanced accuracy và confusion matrix thay vì chỉ dùng accuracy.", ha="center", va="center", fontsize=13.8, color="#0f172a")

    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_split_stacked_panels(*, split_df: pd.DataFrame, output_path: Path) -> None:
    split_order = ["train", "validation", "test", "excluded_gap"]
    split_colors = {
        "train": THESIS_COLORS["green"],
        "validation": THESIS_COLORS["amber"],
        "test": THESIS_COLORS["blue"],
        "excluded_gap": THESIS_COLORS["slate"],
    }
    split_labels = {
        "train": "Huấn luyện",
        "validation": "Xác thực",
        "test": "Kiểm tra",
        "excluded_gap": "Vùng đệm loại bỏ",
    }
    fig, axes = plt.subplots(1, len(SECTION55_EXPERIMENTS), figsize=(12.4, 6.1), sharey=True, facecolor=THESIS_COLORS["canvas"])
    axes_list = axes if isinstance(axes, np.ndarray) else np.asarray([axes])
    for axis, experiment_name in zip(axes_list, SECTION55_EXPERIMENTS, strict=False):
        panel = split_df[split_df["experiment_name"] == experiment_name].copy()
        x_positions = np.arange(len(LABEL_MODES))
        bottoms = np.zeros(len(LABEL_MODES), dtype=float)
        for split_name in split_order:
            values = []
            for label_mode in LABEL_MODES:
                match = panel[(panel["label_mode"] == label_mode) & (panel["split_name"] == split_name)]
                values.append(float(match.iloc[0]["row_count"]) if not match.empty else 0.0)
            axis.bar(x_positions, values, bottom=bottoms, color=split_colors[split_name], label=split_labels[split_name] if experiment_name == "v1" else None, width=0.62)
            bottoms += np.asarray(values)
        axis.set_xticks(x_positions, [_friendly_label_mode(name) for name in LABEL_MODES], rotation=0)
        axis.set_title(experiment_name.upper(), fontsize=14, fontweight="bold", color=THESIS_COLORS["ink"])
        _apply_word_chart_style(axis, y_grid=True, x_grid=False)
    axes_list[0].set_ylabel("Số dòng", fontsize=12, color=THESIS_COLORS["ink"])
    handles, labels = axes_list[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=4, frameon=True)
    fig.suptitle("Hình 5.5a. Số dòng train/validation/test theo các version benchmark", fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"], y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_grouped_bar(
    *,
    frame: pd.DataFrame,
    category_column: str,
    series_column: str,
    value_column: str,
    title: str,
    output_path: Path,
    category_order: list[str],
    series_order: list[str],
    series_colors: list[str],
    y_label: str,
) -> None:
    fig, ax = plt.subplots(figsize=(10.8, 6.0), facecolor=THESIS_COLORS["canvas"])
    x_positions = np.arange(len(category_order))
    bar_width = 0.22
    for index, (series_name, color) in enumerate(zip(series_order, series_colors, strict=False)):
        offsets = x_positions + (index - (len(series_order) - 1) / 2.0) * bar_width
        values = []
        for category_name in category_order:
            match = frame[(frame[category_column] == category_name) & (frame[series_column] == series_name)]
            values.append(float(match.iloc[0][value_column]) if not match.empty else 0.0)
        bars = ax.bar(offsets, values, width=bar_width, color=color, label=_friendly_label_mode(series_name))
        for bar, value in zip(bars, values, strict=False):
            ax.text(bar.get_x() + bar.get_width() / 2.0, value + 1.0, _format_int(value), ha="center", va="bottom", fontsize=9.5, color=THESIS_COLORS["ink"])
    ax.set_xticks(x_positions, [name.upper() for name in category_order])
    ax.set_ylabel("Số dòng", fontsize=12, color=THESIS_COLORS["ink"])
    ax.set_title("Hình 5.5b. Số dòng thuộc vùng đệm loại trừ theo version", fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"], pad=12)
    _apply_word_chart_style(ax, y_grid=True, x_grid=False)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _render_metric_panels(
    *,
    metrics_df: pd.DataFrame,
    metric_column: str,
    title: str,
    output_path: Path,
) -> None:
    fig, axes = plt.subplots(1, len(LABEL_MODES), figsize=(18, 6.2), sharey=True, facecolor=THESIS_COLORS["canvas"])
    axes_list = axes if isinstance(axes, np.ndarray) else np.asarray([axes])
    global_max = float(pd.to_numeric(metrics_df[metric_column], errors="coerce").max()) if not metrics_df.empty else 1.0
    global_limit = min(1.02, max(0.62, global_max + 0.10))
    for axis, label_mode in zip(axes_list, LABEL_MODES, strict=False):
        panel = metrics_df[metrics_df["label_mode"] == label_mode].copy()
        panel["experiment_name"] = panel["experiment_name"].astype(str)
        panel = panel.set_index("experiment_name").reindex(SECTION57_EXPERIMENTS).reset_index()
        values = pd.to_numeric(panel[metric_column], errors="coerce").fillna(0.0).tolist()
        colors = [FOCUS_VERSION_COLORS.get(name, "#cbd5e1") for name in panel["experiment_name"]]
        x_positions = np.arange(len(panel))
        axis.plot(x_positions, values, color=THESIS_COLORS["ink"], linewidth=1.6, alpha=0.75, zorder=2)
        axis.scatter(x_positions, values, s=210, c=colors, edgecolors="#ffffff", linewidths=1.6, zorder=3)
        for x_pos, value, model_name in zip(x_positions, values, panel["selected_model_name"].fillna("").tolist(), strict=False):
            axis.text(
                x_pos,
                value + 0.015,
                f"{value:.3f}\n{MODEL_SHORT_NAMES.get(model_name, model_name)}",
                ha="center",
                va="bottom",
                fontsize=9.2,
            )
        axis.set_xticks(x_positions, [name.upper() for name in panel["experiment_name"]])
        axis.set_title(_friendly_label_mode(label_mode), fontsize=14, fontweight="bold", color=THESIS_COLORS["ink"])
        axis.set_ylim(0.0, global_limit)
        _apply_word_chart_style(axis, y_grid=True, x_grid=False)
    metric_label = "Test macro-F1" if metric_column == "test_macro_f1" else "Test balanced accuracy"
    axes_list[0].set_ylabel(metric_label, fontsize=12, color=THESIS_COLORS["ink"])
    fig.suptitle(title, fontsize=16, fontweight="bold", color=THESIS_COLORS["ink"])
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _build_markdown_summary(
    *,
    dataset_root: Path,
    dataset_build_report_path: Path,
    labeling_report_path: Path,
    section53: dict[str, object],
    section54: dict[str, object],
    section55: dict[str, object],
    section57: dict[str, object],
) -> str:
    lines = [
        "# Chapter 5 Visual Report Pack",
        "",
        "## Scope",
        "",
        "- Muc tieu: bo sung artifact truc quan cho cac muc 5.3, 5.4, 5.5, 5.7 cua Chuong 5.",
        f"- Dataset root duoc doc: `{dataset_root}`",
        f"- Dataset build report: `{dataset_build_report_path}`",
        f"- Labeling report: `{labeling_report_path}`",
        "",
        "## Section 5.3",
        "",
        f"- Output folder: `{section53['section_dir']}`",
        "- `pipeline_overview_counts.csv`: bang tong hop so lieu de dung lai trong bang Chuong 5 hoac infographic.",
        "- `chart_pipeline_overview_infographic.png`: infographic ke chuyen `Firebase raw -> aligned -> labeled -> binary collapse`.",
        "- `chart_raw_source_counts.png`: tong quan so record thiet bi goc truoc khi canh hang.",
        "- `chart_processed_stage_rows.png`: so dong qua aligned -> labeled -> prepared dataset.",
        "- `chart_prepared_rows_heatmap.png`: doi chieu row_count giua cac nhanh nhan va `v0-v3`.",
        "",
        "## Section 5.4",
        "",
        f"- Output folder: `{section54['section_dir']}`",
        "- `chart_label_distribution_panels.png`: 4 panel cho `big_label`, `binary`, `tri_class`, `four_class`; phan bo nay duoc khoa theo snapshot bao cao 01/04/2026-10/05/2026.",
        "",
        "## Section 5.5",
        "",
        f"- Output folder: `{section55['section_dir']}`",
        "- `chart_split_counts_focus_versions.png`: train/validation/test/excluded_gap cho `v1-v2`.",
        "- `chart_excluded_gap_focus_versions.png`: so dong bi loai do gap theo version va nhanh nhan.",
        "- `chart_validation_test_class_support.png`: support tung lop o validation/test cho `v1-v2` de tra loi cau hoi lop hiem co xuat hien hay khong.",
        "",
        "## Section 5.7",
        "",
        f"- Output folder: `{section57['section_dir']}`",
        "- `chart_feature_source_matrix.png`: ma tran thanh phan dac trung cua `v1-v2` de tap trung vao 2 version duoc giu trong phan so sanh dac trung cua so.",
        "- `chart_test_macro_f1_v0_to_v3.png`: gia tri macro-F1 tot nhat tai moi version `v1-v2`; model tot nhat duoc ghi chu tai tung diem.",
        "- `chart_test_balanced_accuracy_v0_to_v3.png`: gia tri balanced accuracy tot nhat tai moi version `v1-v2`.",
        "- `feature_source_registry.csv`: bang giai thich de doi chieu source-kind; hinh metric chinh cua 5.7 hien chi giu `v1-v2`.",
        "",
        "## Interpretation note",
        "",
        "- Trong pham vi bao cao thuc nghiem, muc 5.7 hien chi so sanh `v1-v2` theo dung pham vi dac trung cua so da chot.",
        "- `v0` va `v3-v5` khong con xuat hien trong chart hieu nang chinh cua 5.7; neu can, chi doi chieu lai qua artifact training hoac bang registry.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report = build_visual_pack(args.output_root)
    print(f"Report run: {report['run_id']}")
    print(f"Output folder: {report['output_dir']}")
    print(f"Summary markdown: {report['summary_path']}")


if __name__ == "__main__":
    main()
