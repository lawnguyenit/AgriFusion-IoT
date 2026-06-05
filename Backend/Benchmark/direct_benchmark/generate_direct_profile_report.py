from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT_DIR / "data_profile_report"
DEFAULT_RUN_ROOT = ROOT_DIR / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Word-friendly profile report for direct benchmark raw features.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Path to a direct benchmark run directory. Defaults to the latest run under direct_benchmark/artifacts.",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default="v1",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        help="Which direct experiment to profile.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination folder if it already exists.",
    )
    return parser.parse_args()


def discover_latest_run_dir(output_root: Path) -> Path:
    candidates: list[Path] = []
    for path in output_root.rglob("training_report.json"):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "experiment_reports" in payload and "best_result" in payload:
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No direct benchmark runs found under {output_root}")
    return max((path.parent for path in candidates), key=lambda path: path.stat().st_mtime)


def load_direct_dataset(run_dir: Path, experiment: str) -> pd.DataFrame:
    dataset_path = run_dir / "experiments" / experiment / "direct_dataset.csv"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Direct dataset not found: {dataset_path}")
    frame = pd.read_csv(dataset_path)
    if "split" not in frame.columns or "selected_label_name" not in frame.columns:
        raise ValueError(f"Unexpected direct dataset schema: {dataset_path}")
    return frame


def build_feature_summary(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column in feature_columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        rows.append(
            {
                "feature": column,
                "count": int(series.count()),
                "missing": int(series.isna().sum()),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "min": float(series.min()),
                "p25": float(series.quantile(0.25)),
                "median": float(series.median()),
                "p75": float(series.quantile(0.75)),
                "max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)


def format_summary_frame(summary: pd.DataFrame) -> pd.DataFrame:
    formatted = summary.copy()
    for column in ["mean", "std", "min", "p25", "median", "p75", "max"]:
        formatted[column] = formatted[column].map(lambda value: f"{value:.3f}" if pd.notna(value) else "nan")
    return formatted


def render_table_image(summary: pd.DataFrame, output_path: Path) -> None:
    table_frame = format_summary_frame(summary)
    fig_height = max(6.0, 0.45 * len(table_frame) + 2.0)
    fig, ax = plt.subplots(figsize=(18, fig_height))
    ax.axis("off")
    table = ax.table(
        cellText=table_frame.values,
        colLabels=table_frame.columns.tolist(),
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.25)
    ax.set_title("Direct feature summary table", pad=18, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_boxplots(frame: pd.DataFrame, feature_columns: list[str], output_path: Path) -> None:
    n_features = len(feature_columns)
    n_cols = 3
    n_rows = (n_features + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 4.5 * n_rows))
    axes = axes.flatten()
    for index, column in enumerate(feature_columns):
        ax = axes[index]
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        ax.boxplot(series, vert=True, widths=0.35, patch_artist=True)
        ax.set_title(column, fontsize=10, pad=6)
        ax.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
        ax.grid(axis="y", alpha=0.25)
    for index in range(n_features, len(axes)):
        axes[index].axis("off")
    fig.suptitle("Direct feature distribution boxplots", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_label_donut(frame: pd.DataFrame, output_path: Path) -> None:
    label_counts = frame["selected_label_name"].value_counts().sort_index()
    split_counts = frame["split"].value_counts().sort_index()

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes[0].pie(
        split_counts.values,
        labels=split_counts.index.tolist(),
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        wedgeprops={"width": 0.38, "edgecolor": "white"},
    )
    axes[0].set_title("Rows by split")
    axes[1].pie(
        label_counts.values,
        labels=label_counts.index.tolist(),
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        wedgeprops={"width": 0.38, "edgecolor": "white"},
    )
    axes[1].set_title("Rows by label")
    fig.suptitle("Direct dataset composition", fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_context_timeline_air(frame: pd.DataFrame, output_path: Path) -> None:
    timeline = frame.copy()
    timeline["timestamp_dt"] = pd.to_datetime(timeline["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    fig, ax_air = plt.subplots(figsize=(20, 6))
    ax_air2 = ax_air.twinx()
    air_temp_line = ax_air.plot(
        timeline["timestamp_dt"],
        pd.to_numeric(timeline["air_temp"], errors="coerce"),
        color="#e45756",
        linewidth=1.2,
        label="air_temp",
    )
    air_humidity_line = ax_air2.plot(
        timeline["timestamp_dt"],
        pd.to_numeric(timeline["air_humidity"], errors="coerce"),
        color="#4c78a8",
        linewidth=1.2,
        label="air_humidity",
    )
    ax_air.set_ylabel("air_temp (°C)", color="#e45756")
    ax_air2.set_ylabel("air_humidity (%)", color="#4c78a8")
    ax_air.set_title("Air context")
    ax_air.grid(alpha=0.2)
    ax_air.legend(air_temp_line + air_humidity_line, ["air_temp", "air_humidity"], loc="upper left")
    ax_air.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_air.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_context_timeline_soil(frame: pd.DataFrame, output_path: Path) -> None:
    timeline = frame.copy()
    timeline["timestamp_dt"] = pd.to_datetime(timeline["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    fig, ax_soil = plt.subplots(figsize=(20, 6))
    ax_soil2 = ax_soil.twinx()
    soil_temp_line = ax_soil.plot(
        timeline["timestamp_dt"],
        pd.to_numeric(timeline["soil_temp"], errors="coerce"),
        color="#f58518",
        linewidth=1.2,
        label="soil_temp",
    )
    soil_humidity_line = ax_soil2.plot(
        timeline["timestamp_dt"],
        pd.to_numeric(timeline["soil_humidity"], errors="coerce"),
        color="#54a24b",
        linewidth=1.2,
        label="soil_humidity",
    )
    ax_soil.set_ylabel("soil_temp (°C)", color="#f58518")
    ax_soil2.set_ylabel("soil_humidity (%)", color="#54a24b")
    ax_soil.set_title("Soil physical context")
    ax_soil.grid(alpha=0.2)
    ax_soil.legend(soil_temp_line + soil_humidity_line, ["soil_temp", "soil_humidity"], loc="upper left")
    ax_soil.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_soil.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_context_timeline_chemistry(frame: pd.DataFrame, output_path: Path) -> None:
    timeline = frame.copy()
    timeline["timestamp_dt"] = pd.to_datetime(timeline["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    fig, ax_chem = plt.subplots(figsize=(20, 6))
    chem_columns = ["EC", "pH", "N", "P", "K"]
    cmap = ["#72b7b2", "#b279a2", "#ff9da6", "#9d755d", "#bab0ac"]
    for column, color in zip(chem_columns, cmap, strict=True):
        series = pd.to_numeric(timeline[column], errors="coerce")
        scaled = _min_max_scale(series)
        ax_chem.plot(timeline["timestamp_dt"], scaled, linewidth=1.1, label=f"{column} (norm)", color=color)
    ax_chem.set_ylabel("normalized [0, 1]")
    ax_chem.set_title("Soil chemistry context (min-max normalized)")
    ax_chem.grid(alpha=0.2)
    ax_chem.legend(ncol=5, loc="upper left", fontsize=9)
    ax_chem.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_chem.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _min_max_scale(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    min_value = clean.min()
    max_value = clean.max()
    if pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
        return pd.Series([0.0] * len(clean), index=clean.index)
    return (clean - min_value) / (max_value - min_value)


def generate_report(run_dir: Path, experiment: str, force: bool) -> Path:
    dataset = load_direct_dataset(run_dir, experiment=experiment)
    training_report = json.loads((run_dir / "training_report.json").read_text(encoding="utf-8"))
    experiment_report = next(
        (item for item in training_report.get("experiment_reports", []) if item.get("experiment_name") == experiment),
        None,
    )
    if experiment_report is None:
        raise ValueError(f"Experiment {experiment} not found in training_report.json")

    feature_schema = json.loads((run_dir / "experiments" / experiment / "feature_schema.json").read_text(encoding="utf-8"))
    feature_columns = list(feature_schema["feature_columns"])
    summary = build_feature_summary(dataset, feature_columns)

    run_stamp = datetime.now().strftime("%Y-%m-%d")
    report_root = OUTPUT_ROOT / f"{run_stamp}-profile"
    if report_root.exists() and force:
        for child in report_root.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                import shutil

                shutil.rmtree(child)
    report_root.mkdir(parents=True, exist_ok=True)
    charts_dir = report_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = report_root / f"{experiment}_feature_summary.csv"
    summary.to_csv(summary_csv, index=False)

    render_table_image(summary, charts_dir / f"{experiment}_feature_summary_table.png")
    render_boxplots(dataset, feature_columns, charts_dir / f"{experiment}_feature_boxplots.png")
    render_label_donut(dataset, charts_dir / f"{experiment}_composition_donut.png")
    generated_air = None
    generated_soil = None
    generated_chemistry = None
    if {"air_temp", "air_humidity"}.issubset(dataset.columns):
        generated_air = charts_dir / f"{experiment}_context_air_timeline.png"
        render_context_timeline_air(dataset, generated_air)
    if {"soil_temp", "soil_humidity"}.issubset(dataset.columns):
        generated_soil = charts_dir / f"{experiment}_context_soil_timeline.png"
        render_context_timeline_soil(dataset, generated_soil)
    if {"EC", "pH", "N", "P", "K"}.issubset(dataset.columns):
        generated_chemistry = charts_dir / f"{experiment}_context_chemistry_timeline.png"
        render_context_timeline_chemistry(dataset, generated_chemistry)

    report_md = report_root / f"{experiment}_profile_report.md"
    report_md.write_text(
        "\n".join(
            [
                f"# Direct {experiment.upper()} Profile Report",
                "",
                "## Source",
                f"- run_dir: `{run_dir}`",
                f"- source_kind: `{experiment}`",
                f"- rows: `{len(dataset)}`",
                "",
                "## Key Counts",
                f"- train rows: `{int((dataset['split'] == 'train').sum())}`",
                f"- validation rows: `{int((dataset['split'] == 'validation').sum())}`",
                f"- test rows: `{int((dataset['split'] == 'test').sum())}`",
                f"- excluded gap rows: `{int((dataset['split'] == 'excluded_gap').sum())}`",
                "",
                "## Label Counts",
                *[f"- {label}: `{int(count)}`" for label, count in dataset["selected_label_name"].value_counts().sort_index().items()],
                "",
                "## Feature Summary",
                f"- summary csv: `{summary_csv}`",
                f"- table image: `{charts_dir / f'{experiment}_feature_summary_table.png'}`",
                f"- boxplots: `{charts_dir / f'{experiment}_feature_boxplots.png'}`",
                *([f"- air timeline: `{generated_air}`"] if generated_air is not None else []),
                *([f"- soil timeline: `{generated_soil}`"] if generated_soil is not None else []),
                *([f"- chemistry timeline: `{generated_chemistry}`"] if generated_chemistry is not None else []),
                "",
                "## Composition",
                f"- donut image: `{charts_dir / f'{experiment}_composition_donut.png'}`",
                "",
                "## Notes",
                "- This report is intended for Word insertion as a raw-data evidence pack.",
                "- The feature table uses per-feature min/median/max/quantiles so the distribution is visible without reading the full CSV.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "experiment": experiment,
        "run_dir": str(run_dir),
        "report_root": str(report_root),
        "summary_csv": str(summary_csv),
        "charts": {
            "feature_summary_table": str(charts_dir / f"{experiment}_feature_summary_table.png"),
            "feature_boxplots": str(charts_dir / f"{experiment}_feature_boxplots.png"),
            **(
                {"context_air_timeline": str(generated_air)}
                if generated_air is not None
                else {}
            ),
            **(
                {"context_soil_timeline": str(generated_soil)}
                if generated_soil is not None
                else {}
            ),
            **(
                {"context_chemistry_timeline": str(generated_chemistry)}
                if generated_chemistry is not None
                else {}
            ),
            "composition_donut": str(charts_dir / f"{experiment}_composition_donut.png"),
        },
        "feature_columns": feature_columns,
        "row_count": int(len(dataset)),
        "selected_label_counts": {
            str(label): int(count) for label, count in dataset["selected_label_name"].value_counts().sort_index().items()
        },
    }
    (report_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_root


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve() if args.run_dir is not None else discover_latest_run_dir(DEFAULT_RUN_ROOT)
    report_root = generate_report(run_dir, experiment=args.experiment, force=args.force)
    print(f"Run folder: {run_dir}")
    print(f"Report folder: {report_root}")


if __name__ == "__main__":
    main()
