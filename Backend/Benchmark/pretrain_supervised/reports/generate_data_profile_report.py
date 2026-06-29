from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Backend.Benchmark.common.paths import BENCHMARK_DATASETS_ROOT, PRETRAIN_ROOT
from Backend.Config.runtime import BACKEND_SETTINGS

BASE_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = BENCHMARK_DATASETS_ROOT
PRETRAIN_OUTPUT_ROOT = PRETRAIN_ROOT / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a dataset profile report for Firebase extraction, cleaning, and label scarcity."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to data_profile_report/<YYYY-MM-DD>-profile.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing report artifacts if they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or (BASE_DIR / "data_profile_report" / f"{date.today():%Y-%m-%d}-profile")
    charts_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    source_summary = build_source_summary()
    version_summary = build_version_summary()
    label_summary = build_label_summary()
    source_composition = build_source_composition(source_summary, label_summary)
    abnormal_primary_breakdown = build_abnormal_primary_breakdown()

    source_summary.to_csv(output_dir / "source_summary.csv", index=False)
    version_summary.to_csv(output_dir / "version_cleaning_summary.csv", index=False)
    source_composition.to_csv(output_dir / "source_composition.csv", index=False)
    label_summary["big_label"].to_csv(output_dir / "big_label_distribution.csv", index=False)
    label_summary["event_primary"].to_csv(output_dir / "event_primary_distribution.csv", index=False)
    abnormal_primary_breakdown.to_csv(output_dir / "abnormal_primary_breakdown.csv", index=False)

    report_md = build_markdown_report(source_summary, version_summary, label_summary)
    (output_dir / "data_profile_report.md").write_text(report_md, encoding="utf-8")

    generated = [
        save_figure(
            charts_dir / "data_profile_overview.png",
            lambda fig, axes: plot_overview(fig, axes, source_summary, version_summary, label_summary),
            overwrite=args.force,
            fig_size=(16, 14),
        ),
        save_figure(
            charts_dir / "data_profile_pies.png",
            lambda fig, axes: plot_pies(fig, axes, source_composition, abnormal_primary_breakdown),
            overwrite=args.force,
            fig_size=(16, 10),
        ),
    ]

    manifest = {
        "output_dir": str(output_dir),
        "generated_files": [str(path) for path in generated if path is not None],
        "source_files": {
            "firebase_manifest": str(get_firebase_manifest_path()),
            "layer1_manifest": str(get_layer1_manifest_path()),
            "event_csv": str(get_event_csv_path()),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def get_firebase_manifest_path() -> Path:
    return BACKEND_SETTINGS.source_manifest_path


def get_layer1_manifest_path() -> Path:
    return DATASET_DIR / "manifest.json"


def get_event_csv_path() -> Path:
    return DATASET_DIR / "benchmark_input_labeled.csv"


def build_source_summary() -> pd.DataFrame:
    firebase_manifest = json.loads(get_firebase_manifest_path().read_text(encoding="utf-8"))
    layer1_manifest = json.loads(get_layer1_manifest_path().read_text(encoding="utf-8"))
    event_df = pd.read_csv(get_event_csv_path())

    rows = [
        {
            "stage": "firebase_telemetry_extracted",
            "count": int(firebase_manifest.get("telemetry_record_count", 0)),
            "detail": f"{firebase_manifest.get('telemetry_date_count', 0)} dates; imported_at={firebase_manifest.get('imported_at_utc')}",
        },
        {
            "stage": "layer1_aligned",
            "count": int(layer1_manifest.get("row_count", 0)),
            "detail": "Layer1 alignment manifest",
        },
        {
            "stage": "event_annotated_rows",
            "count": int(len(event_df)),
            "detail": "benchmark_input_labeled.csv",
        },
    ]
    return pd.DataFrame(rows)


def find_latest_pretrain_report(version: str) -> dict[str, object]:
    candidates: list[tuple[float, Path, dict[str, object]]] = []
    for report_path in PRETRAIN_OUTPUT_ROOT.rglob("pretrain_report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if report.get("benchmark_version") != version:
            continue
        candidates.append((report_path.stat().st_mtime, report_path, report))

    if not candidates:
        raise FileNotFoundError(f"No pretrain_report.json found for version {version}")

    _, report_path, report = max(candidates, key=lambda item: (item[0], str(item[1])))
    report["__report_path__"] = str(report_path)
    return report


def build_version_summary() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for version in ["v0", "v1", "v2", "v3", "v4"]:
        report = find_latest_pretrain_report(version)
        downstream_report = find_latest_downstream_report(version)
        row_counts = report.get("row_counts", {}) or {}
        split_counts = report.get("split_counts", {}) or {}
        split_policy = report.get("split_policy", {}) or {}
        label_merge_report, label_policy = extract_label_metadata(downstream_report)
        diagnostics = label_policy.get("diagnostics", {}) or {}

        binary_counts = diagnostics.get("binary_counts_train", {}) or {}
        ternary_counts = diagnostics.get("ternary_counts_train", {}) or {}

        rows.append(
            {
                "version": version,
                "source_kind": report.get("run_label", report.get("run_id", "")),
                "run_id": report.get("run_id", ""),
                "input_csv": Path(str(report.get("input_csv", ""))).name,
                "rows_before_cleaning": int(row_counts.get("before_cleaning", 0)),
                "rows_after_cleaning": int(row_counts.get("after_cleaning", 0)),
                "cleaning_removed_rows": int(row_counts.get("before_cleaning", 0) - row_counts.get("after_cleaning", 0)),
                "train_rows": int(split_counts.get("train", 0)),
                "validation_rows": int(split_counts.get("validation", 0)),
                "test_rows": int(split_counts.get("test", 0)),
                "excluded_gap_rows": int(split_policy.get("excluded_row_count", 0)),
                "gap_minutes": int(split_policy.get("gap_minutes", 0)),
                "merged_labeled_rows": int(label_merge_report.get("labeled_rows", 0)),
                "merged_unlabeled_rows": int(label_merge_report.get("unlabeled_rows", 0)),
                "label_mode_selected": label_policy.get("selected_mode", "unknown"),
                "train_normal": int(binary_counts.get("normal", 0)),
                "train_abnormal": int(binary_counts.get("abnormal", 0)),
                "train_abnormal_ratio": safe_ratio(binary_counts.get("abnormal", 0), diagnostics.get("selected_train_rows", 0)),
                "train_environmental_context": int(ternary_counts.get("environmental_context", 0)),
                "train_operational_or_intervention": int(ternary_counts.get("operational_or_intervention", 0)),
            }
        )

    return pd.DataFrame(rows).sort_values("version", key=_version_sort_key).reset_index(drop=True)


def find_latest_downstream_report(version: str) -> dict[str, object]:
    candidates: list[tuple[float, Path, dict[str, object]]] = []
    for report_path in (BASE_DIR / version / "outputs").rglob("training_report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if report.get("benchmark_version") != version:
            continue
        candidates.append((report_path.stat().st_mtime, report_path, report))

    if not candidates:
        raise FileNotFoundError(f"No training_report.json found for version {version}")

    _, report_path, report = max(candidates, key=lambda item: (item[0], str(item[1])))
    report["__report_path__"] = str(report_path)
    return report


def extract_label_metadata(report: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    if "label_merge_report" in report or "label_policy" in report:
        return report.get("label_merge_report", {}) or {}, report.get("label_policy", {}) or {}

    for experiment_report in report.get("experiment_reports", []) or []:
        if not isinstance(experiment_report, dict):
            continue
        if "label_merge_report" in experiment_report or "label_policy" in experiment_report:
            return (
                experiment_report.get("label_merge_report", {}) or {},
                experiment_report.get("label_policy", {}) or {},
            )

    return {}, {}


def build_label_summary() -> dict[str, pd.DataFrame]:
    event_df = pd.read_csv(get_event_csv_path())
    if "big_label" not in event_df.columns:
        raise KeyError("benchmark_input_labeled.csv does not contain a big_label column")

    big_label_series = event_df["big_label"].fillna("none").astype(str)
    event_primary_series = event_df["event_primary"].fillna("none").astype(str) if "event_primary" in event_df.columns else pd.Series(["none"] * len(event_df))

    big_label_counts = big_label_series.value_counts(dropna=False)
    event_primary_counts = event_primary_series.value_counts(dropna=False)

    big_label_df = pd.DataFrame(
        [
            {
                "label": label,
                "count": int(count),
                "ratio_total": safe_ratio(count, len(event_df)),
            }
            for label, count in big_label_counts.items()
        ]
    ).sort_values("count", ascending=False).reset_index(drop=True)

    event_primary_df = pd.DataFrame(
        [
            {
                "label": label,
                "count": int(count),
                "ratio_total": safe_ratio(count, len(event_df)),
            }
            for label, count in event_primary_counts.items()
        ]
    ).sort_values("count", ascending=False).reset_index(drop=True)

    return {
        "big_label": big_label_df,
        "event_primary": event_primary_df,
    }


def build_source_composition(
    source_summary: pd.DataFrame,
    label_summary: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    firebase_count = int(source_summary.loc[source_summary["stage"] == "firebase_telemetry_extracted", "count"].iloc[0])
    layer1_count = int(source_summary.loc[source_summary["stage"] == "layer1_aligned", "count"].iloc[0])
    cut_count = max(firebase_count - layer1_count, 0)
    rows: list[dict[str, object]] = [
        {
            "category": "cut_before_layer1",
            "count": cut_count,
            "ratio_total": safe_ratio(cut_count, firebase_count),
        }
    ]
    big_label_df = label_summary["big_label"]
    for _, row in big_label_df.iterrows():
        label = str(row["label"])
        count = int(row["count"])
        if label == "none":
            rows.append(
                {
                    "category": "normal",
                    "count": count,
                    "ratio_total": safe_ratio(count, firebase_count),
                }
            )
            continue
        rows.append(
            {
                "category": f"abnormal::{label}",
                "count": count,
                "ratio_total": safe_ratio(count, firebase_count),
            }
        )
    return pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)


def build_abnormal_primary_breakdown() -> pd.DataFrame:
    event_df = pd.read_csv(get_event_csv_path())
    if "event_primary" not in event_df.columns:
        raise KeyError("benchmark_input_labeled.csv does not contain an event_primary column")
    abnormal_df = event_df.loc[event_df["event_primary"].fillna("none").astype(str) != "none"].copy()
    counts = abnormal_df["event_primary"].fillna("none").astype(str).value_counts(dropna=False)
    total_abnormal = len(abnormal_df)
    rows = [
        {
            "category": label,
            "count": int(count),
            "ratio_abnormal": safe_ratio(count, total_abnormal),
        }
        for label, count in counts.items()
    ]
    return pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)


def build_markdown_report(
    source_summary: pd.DataFrame,
    version_summary: pd.DataFrame,
    label_summary: dict[str, pd.DataFrame],
) -> str:
    firebase_row = source_summary.iloc[0]
    layer1_row = source_summary.iloc[1]
    event_row = source_summary.iloc[2]

    total_rows = int(label_summary["big_label"]["count"].sum())
    normal_count = int(label_summary["big_label"].loc[label_summary["big_label"]["label"] == "none", "count"].sum())
    abnormal_count = total_rows - normal_count
    source_composition = build_source_composition(source_summary, label_summary)
    abnormal_primary_breakdown = build_abnormal_primary_breakdown()

    lines = [
        "# Dataset Profile Report",
        "",
        "## 1. Source snapshot",
        "",
        f"- Firebase telemetry extracted: **{int(firebase_row['count'])}**",
        f"- Layer1 aligned rows: **{int(layer1_row['count'])}**",
        f"- Event-annotated rows: **{int(event_row['count'])}**",
        "",
        "### Source table",
        "",
        dataframe_to_markdown(source_summary),
        "",
        "## 2. Train-ready rows by version",
        "",
        "This table shows the latest pretrain run for each version, including the rows that survived cleaning, the actual split rows, and how sparse the abnormal labels are in the train split.",
        "",
        dataframe_to_markdown(version_summary),
        "",
        "## 3. Label collapse before binary merge",
        "",
        f"- Total annotated rows: **{total_rows}**",
        f"- Normal (`big_label == none`): **{normal_count}**",
        f"- Abnormal (`big_label != none`): **{abnormal_count}**",
        f"- Abnormal ratio: **{safe_ratio(abnormal_count, total_rows):.2%}**",
        "",
        "### big_label distribution",
        "",
        dataframe_to_markdown(label_summary["big_label"]),
        "",
        "### event_primary distribution",
        "",
        dataframe_to_markdown(label_summary["event_primary"].head(12)),
        "",
        "## 4. Pie-friendly composition",
        "",
        "### Overall composition from Firebase total",
        "",
        dataframe_to_markdown(source_composition),
        "",
        "### Abnormal event_primary breakdown",
        "",
        dataframe_to_markdown(abnormal_primary_breakdown),
        "",
        "## 5. Interpretation",
        "",
        "- The dataset is small in practice: after alignment and cleaning, each pretrain version sees only about 3.3k rows.",
        "- Abnormal labels are scarce: only a small minority of the annotated rows are non-`none`.",
        "- The train split is heavily imbalanced even before collapse, so downstream metrics should be read with class imbalance in mind.",
    ]
    return "\n".join(lines) + "\n"


def plot_overview(
    fig: plt.Figure,
    axes: np.ndarray,
    source_summary: pd.DataFrame,
    version_summary: pd.DataFrame,
    label_summary: dict[str, pd.DataFrame],
) -> None:
    ax1, ax2, ax3 = axes.flat

    # Panel 1: source counts
    source_labels = [
        "Firebase\ntelemetry",
        "Layer1\naligned",
        "Event\nannotated",
    ]
    source_counts = source_summary["count"].astype(int).tolist()
    bars = ax1.bar(source_labels, source_counts, color=["#4C78A8", "#72B7B2", "#F58518"], width=0.6)
    ax1.set_title("Pipeline source counts")
    ax1.set_ylabel("Rows")
    annotate_bars(ax1, bars, fmt="{:,.0f}")
    ax1.grid(axis="y", alpha=0.2)

    # Panel 2: cleaned rows and train rows by version
    versions = version_summary["version"].tolist()
    cleaned = version_summary["rows_after_cleaning"].astype(int).tolist()
    train_rows = version_summary["train_rows"].astype(int).tolist()
    x = np.arange(len(versions))
    width = 0.34
    bars_cleaned = ax2.bar(x - width / 2, cleaned, width=width, label="after cleaning", color="#54A24B")
    bars_train = ax2.bar(x + width / 2, train_rows, width=width, label="train split", color="#E45756")
    ax2.set_xticks(x)
    ax2.set_xticklabels(versions)
    ax2.set_title("Cleaned rows vs train split by version")
    ax2.set_ylabel("Rows")
    annotate_bars(ax2, bars_cleaned, fmt="{:,.0f}")
    annotate_bars(ax2, bars_train, fmt="{:,.0f}")
    for idx, row in version_summary.iterrows():
        ax2.text(
            x[idx],
            max(int(row["rows_after_cleaning"]), int(row["train_rows"])) + 25,
            f"abn {int(row['train_abnormal'])}/{int(row['train_rows'])} ({float(row['train_abnormal_ratio']):.1%})",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax2.legend(frameon=False)
    ax2.grid(axis="y", alpha=0.2)

    # Panel 3: big label collapse
    big_label_df = label_summary["big_label"].copy()
    big_label_df = big_label_df.sort_values("count", ascending=True)
    bars = ax3.barh(big_label_df["label"], big_label_df["count"].astype(int), color="#B279A2")
    ax3.set_title("big_label distribution before binary collapse")
    ax3.set_xlabel("Rows")
    annotate_horizontal_bars(ax3, bars, big_label_df["count"].astype(int).tolist(), big_label_df["ratio_total"].astype(float).tolist())
    ax3.grid(axis="x", alpha=0.2)

    fig.tight_layout()


def plot_pies(
    fig: plt.Figure,
    axes: np.ndarray,
    source_composition: pd.DataFrame,
    abnormal_primary_breakdown: pd.DataFrame,
) -> None:
    ax1, ax2, ax3 = axes.flat
    ax3.axis("off")
    fig.suptitle("Dataset composition for report writing", fontsize=16, y=0.98)

    labels = source_composition["category"].astype(str).tolist()
    counts = source_composition["count"].astype(int).tolist()
    colors = build_palette(len(labels))
    ax1.pie(
        counts,
        labels=None,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        autopct=lambda pct: format_pct_if_large(pct, counts),
        pctdistance=0.78,
    )
    ax1.set_title("Firebase total -> cut / normal / abnormal buckets")
    ax1.legend(
        labels=[f"{label.replace('abnormal::', '')} ({count:,})" for label, count in zip(labels, counts, strict=False)],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=8,
    )
    ax1.set_aspect("equal")

    abnormal_counts = abnormal_primary_breakdown["count"].astype(int).tolist()
    abnormal_labels = abnormal_primary_breakdown["category"].astype(str).tolist()
    colors = build_palette(len(abnormal_labels))
    ax2.pie(
        abnormal_counts,
        labels=None,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        autopct=lambda pct: format_pct_if_large(pct, abnormal_counts),
        pctdistance=0.78,
    )
    ax2.set_title("Abnormal rows -> event_primary breakdown")
    ax2.legend(
        labels=[f"{label} ({count:,})" for label, count in zip(abnormal_labels, abnormal_counts, strict=False)],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=8,
    )
    ax2.set_aspect("equal")

    fig.tight_layout()


def save_figure(path: Path, draw_fn, overwrite: bool = False, fig_size: tuple[int, int] = (14, 10)) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Use --force to overwrite.")

    fig, axes = plt.subplots(3, 1, figsize=fig_size, constrained_layout=False)
    draw_fn(fig, axes)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def annotate_bars(ax: plt.Axes, bars: Iterable[plt.Rectangle], fmt: str = "{:,.2f}") -> None:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt.format(height),
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def annotate_horizontal_bars(ax: plt.Axes, bars: Iterable[plt.Rectangle], counts: list[int], ratios: list[float]) -> None:
    for bar, count, ratio in zip(bars, counts, ratios, strict=False):
        width = bar.get_width()
        ax.annotate(
            f"{count:,} ({ratio:.1%})",
            xy=(width, bar.get_y() + bar.get_height() / 2),
            xytext=(4, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=8,
        )


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"

    frame = df.copy()
    for column in frame.columns:
        if pd.api.types.is_float_dtype(frame[column]):
            frame[column] = frame[column].map(lambda value: f"{value:.4f}" if pd.notna(value) else "")
    headers = list(frame.columns)
    rows = frame.astype(str).values.tolist()
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values)) + " |"

    separator = "| " + " | ".join("-" * width for width in widths) + " |"
    lines = [format_row(headers), separator]
    for row in rows:
        lines.append(format_row(row))
    return "\n".join(lines)


def build_palette(size: int) -> list[str]:
    cmap = plt.get_cmap("tab20")
    if size <= 20:
        return [cmap(i) for i in range(size)]
    return [cmap(i % 20) for i in range(size)]


def format_pct_if_large(pct: float, counts: list[int]) -> str:
    total = sum(counts)
    value = pct * total / 100.0
    if total <= 0 or value < 10:
        return ""
    return f"{pct:.1f}%"


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    denominator = float(denominator)
    if denominator == 0:
        return 0.0
    return float(numerator) / denominator


def _version_sort_key(series: pd.Series) -> pd.Series:
    order = {"v0": 0, "v1": 1, "v2": 2, "v3": 3, "v4": 4}
    return series.map(lambda value: order.get(str(value), 999))


if __name__ == "__main__":
    main()
