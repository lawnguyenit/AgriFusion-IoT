from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from Backend.Benchmark.common.raw_tabular_dataset import build_raw_tabular_source_registry
from Backend.Benchmark.tabular_benchmark.src.config.settings import (
    default_dataset_output_root,
    default_report_output_root,
    default_training_output_root,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "Backend"
LAYER0_ROOT = BACKEND_DIR / "Output_data" / "Layer0" / "Firebase_data"
LAYER1_ROOT = BACKEND_DIR / "Output_data" / "Layer1"
BENCHMARK_DATASET_ROOT = BACKEND_DIR / "Benchmark" / "benchmark_dataset" / "dataset"
FRONTEND_INDEX = ROOT_DIR / "Frontend" / "public" / "index.html"

LABEL_COLUMNS = ("event_primary", "big_label", "binary", "tri_class", "four_class")
EXCLUDED_LABEL_COLUMNS = [
    "event_primary",
    "big_label",
    "binary",
    "tri_class",
    "four_class",
    "selected_label_name",
    "selected_label_id",
]
LEAKAGE_CHECKLIST = [
    "Khong dua event_*, event_primary, big_label, binary, tri_class, four_class vao feature.",
    "Khong dung cot next/lead/future/gap_to_next lam feature dau vao.",
    "v2 chi dung cua so nhin ve qua khu.",
    "Split temporal co purge gap khi feature co lookback.",
    "Van ton tai proxy leakage gian tiep vi feature co the phan anh lai rule gan nhan.",
]
LIMITATIONS = [
    "Weak labels khong phai ground truth nong hoc doc lap.",
    "Class imbalance cua tri_class va four_class van rat cao.",
    "v2 co the hoc lai mot phan rule telemetry neu labels cung dua vao bien dong.",
    "Benchmark result chi the hien kha nang telemetry classification, khong phai quyet dinh canh tac.",
]


@dataclass(frozen=True)
class RunPointer:
    root: Path
    marker: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit helpers for DemoUI pipeline dashboard.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("overview")
    subparsers.add_parser("raw-count")
    subparsers.add_parser("validate-layer1")
    subparsers.add_parser("sensor-quality")
    subparsers.add_parser("telemetry-gaps")
    subparsers.add_parser("preview-aligned")
    subparsers.add_parser("alignment-summary")
    subparsers.add_parser("label-distribution")
    subparsers.add_parser("label-mapping")
    subparsers.add_parser("label-audit-report")
    subparsers.add_parser("preview-labeled")
    subparsers.add_parser("feature-compare")
    feature_summary = subparsers.add_parser("feature-summary")
    feature_summary.add_argument("--version", choices=("v0", "v1", "v2"), required=True)
    subparsers.add_parser("feature-nan-check")
    split_summary = subparsers.add_parser("split-summary")
    split_summary.add_argument("--label-mode", choices=("binary", "tri_class", "four_class"), default="binary")
    rare_class = subparsers.add_parser("rare-class-coverage")
    rare_class.add_argument("--label-mode", choices=("binary", "tri_class", "four_class"), default="binary")
    purge_gap = subparsers.add_parser("purge-gap")
    purge_gap.add_argument("--label-mode", choices=("binary", "tri_class", "four_class"), default="binary")
    subparsers.add_parser("prepare-all-lanes")
    training_features = subparsers.add_parser("training-feature-columns")
    training_features.add_argument("--label-mode", choices=("binary", "tri_class", "four_class"), default="binary")
    subparsers.add_parser("excluded-label-columns")
    subparsers.add_parser("leakage-checklist")
    subparsers.add_parser("limitations-summary")
    subparsers.add_parser("export-defense-audit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command = args.command

    if command == "overview":
        _print_json(collect_pipeline_overview())
        return
    if command == "raw-count":
        _print_text(raw_count_summary())
        return
    if command == "validate-layer1":
        _print_text(validate_layer1_summary())
        return
    if command == "sensor-quality":
        _print_text(sensor_quality_summary())
        return
    if command == "telemetry-gaps":
        _print_text(telemetry_gap_summary())
        return
    if command == "preview-aligned":
        _print_text(preview_csv_summary(BENCHMARK_DATASET_ROOT / "benchmark_input_aligned.csv"))
        return
    if command == "alignment-summary":
        _print_text(alignment_summary())
        return
    if command == "label-distribution":
        _print_text(label_distribution_summary())
        return
    if command == "label-mapping":
        _print_text(label_mapping_summary())
        return
    if command == "label-audit-report":
        _print_text(label_audit_report_summary())
        return
    if command == "preview-labeled":
        _print_text(preview_csv_summary(BENCHMARK_DATASET_ROOT / "benchmark_input_labeled.csv"))
        return
    if command == "feature-compare":
        _print_text(feature_compare_summary())
        return
    if command == "feature-summary":
        _print_text(feature_version_summary(args.version))
        return
    if command == "feature-nan-check":
        _print_text(feature_nan_summary())
        return
    if command == "split-summary":
        _print_text(split_summary_text(args.label_mode))
        return
    if command == "rare-class-coverage":
        _print_text(rare_class_coverage_text(args.label_mode))
        return
    if command == "purge-gap":
        _print_text(purge_gap_text(args.label_mode))
        return
    if command == "prepare-all-lanes":
        _print_text(prepare_all_lanes_plan())
        return
    if command == "training-feature-columns":
        _print_text(training_feature_columns_text(args.label_mode))
        return
    if command == "excluded-label-columns":
        _print_text("\n".join(EXCLUDED_LABEL_COLUMNS))
        return
    if command == "leakage-checklist":
        _print_text("\n".join(f"- {item}" for item in LEAKAGE_CHECKLIST))
        return
    if command == "limitations-summary":
        _print_text("\n".join(f"- {item}" for item in LIMITATIONS))
        return
    if command == "export-defense-audit":
        _print_text(export_defense_audit())
        return


def collect_pipeline_overview() -> dict[str, Any]:
    return {
        "ingestion": build_ingestion_overview(),
        "layer1": build_layer1_overview(),
        "aligned_table": build_aligned_overview(),
        "weak_labeling": build_weak_labeling_overview(),
        "feature_engineering": build_feature_overview(),
        "temporal_split": build_temporal_split_overview(),
        "benchmarking": build_benchmarking_overview(),
        "report_publish": build_report_publish_overview(),
        "defense_backup": build_defense_overview(),
    }


def build_ingestion_overview() -> dict[str, Any]:
    history_files = sorted((LAYER0_ROOT / "history").rglob("*.json"))
    latest_meta = LAYER0_ROOT / "new_raw" / "latest_meta.json"
    sync_state = LAYER0_ROOT / "new_raw" / "sync_state.json"
    date_range = _history_date_range_from_paths(history_files)
    return {
        "raw_record_count": len(history_files),
        "history_date_range": date_range,
        "last_pull_at": _safe_mtime(sync_state) or _safe_mtime(latest_meta),
        "output_root": str(LAYER0_ROOT),
        "latest_meta_exists": latest_meta.exists(),
    }


def build_layer1_overview() -> dict[str, Any]:
    manifest = _read_json(LAYER1_ROOT / "manifest.json")
    sensor_counts = {
        stream: _count_jsonl_lines(LAYER1_ROOT / stream / "history.jsonl")
        for stream in ("sht30", "npk", "meteo")
    }
    processed = int(manifest.get("processed_source_records", 0) or 0)
    filtered = int(manifest.get("filtered_out_records", 0) or 0)
    accepted = max(processed - filtered, 0)
    valid_ratio = round((accepted / processed), 4) if processed else None
    return {
        "sensor_counts": sensor_counts,
        "processed_source_records": processed,
        "filtered_out_records": filtered,
        "valid_ratio": valid_ratio,
        "last_manifest_at": _safe_mtime(LAYER1_ROOT / "manifest.json"),
    }


def build_aligned_overview() -> dict[str, Any]:
    aligned_csv = BENCHMARK_DATASET_ROOT / "benchmark_input_aligned.csv"
    if not aligned_csv.exists():
        return {"exists": False}
    frame = _read_csv(aligned_csv)
    timestamps = _timestamp_series(frame)
    gap_summary = _gap_summary(timestamps)
    sensor_columns = [column for column in ("soil_temp", "soil_humidity", "air_temp", "air_humidity", "EC", "pH", "N", "P", "K") if column in frame.columns]
    missing_sensor_rows = int(frame[sensor_columns].isna().any(axis=1).sum()) if sensor_columns else None
    return {
        "exists": True,
        "row_count": int(len(frame)),
        "start_ts": _first_int(timestamps),
        "end_ts": _last_int(timestamps),
        "median_sampling_sec": gap_summary["median_gap_sec"],
        "gap_gt_15m": gap_summary["gap_gt_15m"],
        "gap_gt_30m": gap_summary["gap_gt_30m"],
        "gap_gt_60m": gap_summary["gap_gt_60m"],
        "missing_sensor_rows": missing_sensor_rows,
        "path": str(aligned_csv),
    }


def build_weak_labeling_overview() -> dict[str, Any]:
    labeled_csv = BENCHMARK_DATASET_ROOT / "benchmark_input_labeled.csv"
    if not labeled_csv.exists():
        return {"exists": False}
    frame = _read_csv(labeled_csv)
    counts = {
        column: _value_counts(frame, column)
        for column in ("big_label", "binary", "tri_class", "four_class")
        if column in frame.columns
    }
    big_label_counts = counts.get("big_label", {})
    non_normal = sum(count for label, count in big_label_counts.items() if str(label).lower() not in {"normal", "none", "nan"})
    return {
        "exists": True,
        "row_count": int(len(frame)),
        "big_label_counts": big_label_counts,
        "binary_counts": counts.get("binary", {}),
        "tri_class_counts": counts.get("tri_class", {}),
        "four_class_counts": counts.get("four_class", {}),
        "none_or_normal_rows": int(big_label_counts.get("normal", 0) + big_label_counts.get("none", 0)),
        "non_normal_rows": int(non_normal),
        "class_imbalance_ratio": _imbalance_ratio(big_label_counts),
    }


def build_feature_overview() -> dict[str, Any]:
    return {
        "v0": _feature_version_overview("v0"),
        "v1": _feature_version_overview("v1"),
        "v2": _feature_version_overview("v2"),
    }


def build_temporal_split_overview() -> dict[str, Any]:
    return {
        lane: _dataset_lane_overview(lane)
        for lane in ("binary", "tri_class", "four_class")
    }


def build_benchmarking_overview() -> dict[str, Any]:
    return {
        lane: _training_lane_overview(lane)
        for lane in ("binary", "tri_class", "four_class")
    }


def build_report_publish_overview() -> dict[str, Any]:
    return {
        lane: _report_lane_overview(lane)
        for lane in ("binary", "tri_class", "four_class")
    }


def build_defense_overview() -> dict[str, Any]:
    return {
        "feature_versions": build_feature_overview(),
        "excluded_label_columns": list(EXCLUDED_LABEL_COLUMNS),
        "leakage_checklist": list(LEAKAGE_CHECKLIST),
        "limitations": list(LIMITATIONS),
    }


def raw_count_summary() -> str:
    overview = build_ingestion_overview()
    return "\n".join(
        [
            "RAW COUNT SUMMARY",
            f"Layer0 root: {overview['output_root']}",
            f"Raw record count: {overview['raw_record_count']}",
            f"History range: {overview['history_date_range']}",
            f"Last pull: {overview['last_pull_at'] or 'unknown'}",
        ]
    )


def validate_layer1_summary() -> str:
    overview = build_layer1_overview()
    return "\n".join(
        [
            "LAYER1 VALIDATION",
            f"Manifest updated: {overview['last_manifest_at'] or 'missing'}",
            f"Processed source records: {overview['processed_source_records']}",
            f"Filtered source records: {overview['filtered_out_records']}",
            f"Valid ratio: {overview['valid_ratio']}",
            f"Snapshot counts: {json.dumps(overview['sensor_counts'], ensure_ascii=True)}",
        ]
    )


def sensor_quality_summary() -> str:
    overview = build_layer1_overview()
    return "\n".join(
        [
            "SENSOR QUALITY SUMMARY",
            f"SHT30 snapshots: {overview['sensor_counts'].get('sht30', 0)}",
            f"NPK snapshots: {overview['sensor_counts'].get('npk', 0)}",
            f"Meteo snapshots: {overview['sensor_counts'].get('meteo', 0)}",
            f"Filtered records: {overview['filtered_out_records']}",
            f"Valid ratio: {overview['valid_ratio']}",
        ]
    )


def telemetry_gap_summary() -> str:
    overview = build_aligned_overview()
    if not overview.get("exists"):
        return "Aligned CSV not found."
    return "\n".join(
        [
            "TELEMETRY GAP SUMMARY",
            f"Row count: {overview['row_count']}",
            f"Timestamp range: {overview['start_ts']} -> {overview['end_ts']}",
            f"Median sampling sec: {overview['median_sampling_sec']}",
            f"Gaps > 15m: {overview['gap_gt_15m']}",
            f"Gaps > 30m: {overview['gap_gt_30m']}",
            f"Gaps > 60m: {overview['gap_gt_60m']}",
            f"Missing sensor rows: {overview['missing_sensor_rows']}",
        ]
    )


def preview_csv_summary(path: Path, rows: int = 5) -> str:
    if not path.exists():
        return f"CSV not found: {path}"
    frame = _read_csv(path)
    head = frame.head(rows).to_string(index=False)
    tail = frame.tail(rows).to_string(index=False)
    return "\n".join(
        [
            f"CSV PREVIEW: {path}",
            f"Rows: {len(frame)}",
            "",
            "[HEAD]",
            head,
            "",
            "[TAIL]",
            tail,
        ]
    )


def alignment_summary() -> str:
    overview = build_aligned_overview()
    return json.dumps(overview, indent=2, ensure_ascii=True)


def label_distribution_summary() -> str:
    overview = build_weak_labeling_overview()
    if not overview.get("exists"):
        return "Labeled CSV not found."
    return "\n".join(
        [
            "WEAK LABEL DISTRIBUTION",
            f"Rows: {overview['row_count']}",
            f"big_label: {json.dumps(overview['big_label_counts'], ensure_ascii=True)}",
            f"binary: {json.dumps(overview['binary_counts'], ensure_ascii=True)}",
            f"tri_class: {json.dumps(overview['tri_class_counts'], ensure_ascii=True)}",
            f"four_class: {json.dumps(overview['four_class_counts'], ensure_ascii=True)}",
            f"Class imbalance ratio: {overview['class_imbalance_ratio']}",
        ]
    )


def label_mapping_summary() -> str:
    labeled_csv = BENCHMARK_DATASET_ROOT / "benchmark_input_labeled.csv"
    if not labeled_csv.exists():
        return "Labeled CSV not found."
    frame = _read_csv(labeled_csv)
    required = [column for column in LABEL_COLUMNS if column in frame.columns]
    mapping = frame[required].drop_duplicates().sort_values(required).head(50)
    return "\n".join(
        [
            "LABEL MAPPING PREVIEW",
            f"Columns: {required}",
            mapping.to_string(index=False),
        ]
    )


def label_audit_report_summary() -> str:
    path = BENCHMARK_DATASET_ROOT / "benchmark_labeling_report.json"
    payload = _read_json(path)
    return "\n".join(
        [
            f"Label audit report path: {path}",
            json.dumps(payload, indent=2, ensure_ascii=True),
        ]
    )


def _feature_version_overview(version: str) -> dict[str, Any]:
    registry = build_raw_tabular_source_registry()
    spec = registry[version]
    source_paths = [BENCHMARK_DATASET_ROOT / name for name in spec.source_csv_names]
    existing_paths = [path for path in source_paths if path.exists()]
    if not existing_paths:
        return {
            "version": version,
            "exists": False,
            "source_csv_names": list(spec.source_csv_names),
            "feature_count": len(spec.feature_columns),
        }
    frame = _read_csv(existing_paths[0])
    available_columns = [column for column in spec.feature_columns if column in frame.columns]
    nan_rows = int(frame[available_columns].isna().any(axis=1).sum()) if available_columns else 0
    return {
        "version": version,
        "exists": True,
        "source_csv_names": list(spec.source_csv_names),
        "feature_count": len(spec.feature_columns),
        "row_count": int(len(frame)),
        "available_feature_count": len(available_columns),
        "nan_rows": nan_rows,
        "feature_columns": list(spec.feature_columns),
        "description": spec.description,
    }


def feature_version_summary(version: str) -> str:
    return json.dumps(_feature_version_overview(version), indent=2, ensure_ascii=True)


def feature_compare_summary() -> str:
    payload = build_feature_overview()
    return json.dumps(payload, indent=2, ensure_ascii=True)


def feature_nan_summary() -> str:
    payload = {
        version: {
            "exists": item.get("exists"),
            "row_count": item.get("row_count"),
            "feature_count": item.get("feature_count"),
            "nan_rows": item.get("nan_rows"),
        }
        for version, item in build_feature_overview().items()
    }
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _dataset_lane_overview(label_mode: str) -> dict[str, Any]:
    latest_dir = _find_latest_run(RunPointer(default_dataset_output_root(label_mode), "dataset_manifest.json"))
    if latest_dir is None:
        return {"exists": False}
    manifest = _read_json(latest_dir / "dataset_manifest.json")
    experiment_reports = manifest.get("experiment_reports", [])
    focus_summary = {}
    for experiment_name in ("v0", "v1", "v2"):
        split_path = latest_dir / "experiments" / experiment_name / "split_label_summary.json"
        if split_path.exists():
            focus_summary[experiment_name] = _read_json(split_path)
    return {
        "exists": True,
        "latest_run_dir": str(latest_dir),
        "experiments": manifest.get("experiments", []),
        "experiment_count": len(experiment_reports) if isinstance(experiment_reports, list) else 0,
        "focus_summary": focus_summary,
        "last_run_at": _safe_mtime(latest_dir / "dataset_manifest.json"),
    }


def split_summary_text(label_mode: str) -> str:
    return json.dumps(_dataset_lane_overview(label_mode), indent=2, ensure_ascii=True)


def rare_class_coverage_text(label_mode: str) -> str:
    overview = _dataset_lane_overview(label_mode)
    if not overview.get("exists"):
        return f"No dataset build run found for {label_mode}."
    warnings: list[str] = []
    for experiment_name, summary in overview.get("focus_summary", {}).items():
        for split_name in ("validation", "test"):
            counts = summary.get(split_name, {}).get("selected_label_counts", {})
            zero_like = [label for label, count in counts.items() if int(count) == 0]
            if zero_like:
                warnings.append(f"{experiment_name}/{split_name} missing classes: {zero_like}")
    if not warnings:
        warnings.append("No zero-count class warning found in focus v0/v1/v2 summaries.")
    return "\n".join(warnings)


def purge_gap_text(label_mode: str) -> str:
    overview = _dataset_lane_overview(label_mode)
    if not overview.get("exists"):
        return f"No dataset build run found for {label_mode}."
    lines = []
    for experiment_name, summary in overview.get("focus_summary", {}).items():
        excluded = summary.get("excluded_gap", {})
        lines.append(
            f"{experiment_name}: excluded_gap rows={excluded.get('row_count', 0)} "
            f"labels={json.dumps(excluded.get('selected_label_counts', {}), ensure_ascii=True)}"
        )
    return "\n".join(lines) if lines else "No focus summaries found."


def prepare_all_lanes_plan() -> str:
    return "\n".join(
        [
            "Prepare all benchmark configs plan:",
            "python Backend/Benchmark/tabular_benchmark/prepare.py --label-mode binary",
            "python Backend/Benchmark/tabular_benchmark/prepare.py --label-mode tri_class",
            "python Backend/Benchmark/tabular_benchmark/prepare.py --label-mode four_class",
        ]
    )


def _training_lane_overview(label_mode: str) -> dict[str, Any]:
    latest_dir = _find_latest_run(RunPointer(default_training_output_root(label_mode), "training_report.json"))
    if latest_dir is None:
        return {"exists": False}
    report = _read_json(latest_dir / "training_report.json")
    best_result = report.get("best_result", {})
    return {
        "exists": True,
        "latest_run_dir": str(latest_dir),
        "best_result": best_result,
        "last_run_at": _safe_mtime(latest_dir / "training_report.json"),
    }


def _report_lane_overview(label_mode: str) -> dict[str, Any]:
    latest_dir = _find_latest_run(RunPointer(default_report_output_root(label_mode), "report_manifest.json"))
    if latest_dir is None:
        return {"exists": False}
    manifest = _read_json(latest_dir / "report_manifest.json")
    return {
        "exists": True,
        "latest_run_dir": str(latest_dir),
        "summary_metrics_path": manifest.get("summary_metrics_path"),
        "report_summary_path": manifest.get("report_summary_path"),
        "last_run_at": _safe_mtime(latest_dir / "report_manifest.json"),
    }


def training_feature_columns_text(label_mode: str) -> str:
    latest_dir = _find_latest_run(RunPointer(default_dataset_output_root(label_mode), "dataset_manifest.json"))
    if latest_dir is None:
        return f"No dataset build run found for {label_mode}."
    lines = [f"Feature schemas from latest dataset run: {latest_dir}"]
    for experiment_name in ("v0", "v1", "v2"):
        schema_path = latest_dir / "experiments" / experiment_name / "feature_schema.json"
        if not schema_path.exists():
            continue
        payload = _read_json(schema_path)
        lines.append(f"[{experiment_name}]")
        lines.extend(str(column) for column in payload.get("feature_columns", []))
    return "\n".join(lines)


def export_defense_audit() -> str:
    overview = {
        "weak_labeling": build_weak_labeling_overview(),
        "feature_engineering": build_feature_overview(),
        "temporal_split": build_temporal_split_overview(),
        "benchmarking": build_benchmarking_overview(),
        "excluded_label_columns": EXCLUDED_LABEL_COLUMNS,
        "leakage_checklist": LEAKAGE_CHECKLIST,
        "limitations": LIMITATIONS,
    }
    return json.dumps(overview, indent=2, ensure_ascii=True)


def _find_latest_run(pointer: RunPointer) -> Path | None:
    root = pointer.root
    if not root.exists():
        return None
    candidates = [path.parent for path in root.rglob(pointer.marker) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _history_date_range_from_paths(paths: list[Path]) -> str:
    if not paths:
        return "unknown"
    tokens = []
    for path in paths:
        try:
            year = path.parents[2].name
            month = path.parents[1].name
            day = path.parent.name
            tokens.append(f"{year}-{month}-{day}")
        except Exception:
            continue
    if not tokens:
        return "unknown"
    return f"{min(tokens)} -> {max(tokens)}"


def _safe_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.stat().st_mtime_ns and path.stat().st_mtime and pd.Timestamp(path.stat().st_mtime, unit="s").isoformat()


def _count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def _timestamp_series(frame: pd.DataFrame) -> pd.Series:
    if "timestamp" not in frame.columns:
        return pd.Series(dtype="float64")
    series = pd.to_numeric(frame["timestamp"], errors="coerce").dropna().astype("int64")
    return series.sort_values(ignore_index=True)


def _gap_summary(series: pd.Series) -> dict[str, int | None]:
    if len(series) < 2:
        return {
            "median_gap_sec": None,
            "gap_gt_15m": 0,
            "gap_gt_30m": 0,
            "gap_gt_60m": 0,
        }
    gaps = [int(later - earlier) for earlier, later in zip(series[:-1], series[1:]) if later >= earlier]
    return {
        "median_gap_sec": int(median(gaps)) if gaps else None,
        "gap_gt_15m": sum(1 for gap in gaps if gap > 15 * 60),
        "gap_gt_30m": sum(1 for gap in gaps if gap > 30 * 60),
        "gap_gt_60m": sum(1 for gap in gaps if gap > 60 * 60),
    }


def _value_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    return {
        str(label): int(count)
        for label, count in frame[column].fillna("none").value_counts(dropna=False).sort_index().items()
    }


def _imbalance_ratio(counts: dict[str, int]) -> float | None:
    positive = [count for count in counts.values() if count > 0]
    if len(positive) < 2:
        return None
    return round(min(positive) / max(positive), 4)


def _first_int(series: pd.Series) -> int | None:
    return int(series.iloc[0]) if not series.empty else None


def _last_int(series: pd.Series) -> int | None:
    return int(series.iloc[-1]) if not series.empty else None


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def _print_text(text: str) -> None:
    print(text)


if __name__ == "__main__":
    main()
