from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.benchmark_dataset.alignment.config import AlignmentConfig, default_input_root, default_output_root
from Backend.Benchmark.benchmark_dataset.alignment.main import run_alignment
from Backend.Benchmark.benchmark_dataset.multi_window_features.src.pipeline import build_multi_window_experiments
from Backend.Benchmark.benchmark_dataset.real_labeling.src.pipeline import build_real_event_labels
from Backend.Benchmark.benchmark_dataset.reporting import build_stage_report, utc_now_iso, write_report
from Backend.Benchmark.benchmark_dataset.single_window_features.src.pipeline import build_single_window_experiments


SINGLE_WINDOW_EXPERIMENTS = ("exp1", "exp2", "exp3", "exp4", "exp5", "exp6")
MULTI_WINDOW_EXPERIMENTS = ("combo1", "combo2", "combo3", "combo4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the active benchmark dataset package from Layer1 histories."
    )
    parser.add_argument("--input-root", type=Path, default=default_input_root(), help="Layer1 root directory.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root(),
        help="Benchmark dataset output directory.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for a dry run.")
    parser.add_argument(
        "--anchor-cluster-gap-sec",
        type=int,
        default=300,
        help="Cluster timestamps within this gap into one master timestamp.",
    )
    parser.add_argument(
        "--family-match-tolerance-sec",
        type=int,
        default=1200,
        help="Maximum allowed time offset when joining a family record to a master timestamp.",
    )
    parser.add_argument(
        "--aligned-csv",
        type=Path,
        default=None,
        help="Reuse an existing benchmark_input_aligned.csv. Only valid with --skip-alignment.",
    )
    parser.add_argument(
        "--skip-alignment",
        action="store_true",
        help="Reuse an existing aligned CSV and skip benchmark alignment rebuild.",
    )
    parser.add_argument(
        "--skip-real-labeling",
        action="store_true",
        help="Skip rebuilding benchmark_input_labeled.csv from Layer0 Firebase metadata.",
    )
    parser.add_argument(
        "--skip-single-window-features",
        action="store_true",
        help="Skip single-window feature exports.",
    )
    parser.add_argument(
        "--skip-multi-window-features",
        action="store_true",
        help="Skip multi-window feature exports.",
    )
    parser.add_argument(
        "--single-window-experiments",
        nargs="+",
        choices=SINGLE_WINDOW_EXPERIMENTS,
        default=None,
        help="Optional subset of single-window feature exports to generate.",
    )
    parser.add_argument(
        "--multi-window-experiments",
        nargs="+",
        choices=MULTI_WINDOW_EXPERIMENTS,
        default=None,
        help="Optional subset of multi-window feature exports to generate.",
    )
    args = parser.parse_args()
    validate_args(args, parser)
    return args


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.aligned_csv is not None and not args.skip_alignment:
        parser.error("--aligned-csv is only valid with --skip-alignment.")
    if args.skip_alignment and args.limit is not None:
        parser.error("--limit can only be used when alignment is rebuilt.")
    if args.skip_alignment and args.anchor_cluster_gap_sec != 300:
        parser.error("--anchor-cluster-gap-sec can only be used when alignment is rebuilt.")
    if args.skip_alignment and args.family_match_tolerance_sec != 1200:
        parser.error("--family-match-tolerance-sec can only be used when alignment is rebuilt.")
    if (
        args.skip_alignment
        and args.skip_real_labeling
        and args.skip_single_window_features
        and args.skip_multi_window_features
    ):
        parser.error("Nothing to build. Enable at least one stage or remove --skip-alignment.")


def build_alignment_config(args: argparse.Namespace) -> AlignmentConfig:
    return AlignmentConfig(
        input_root=args.input_root.resolve(),
        output_root=args.output_root.resolve(),
        anchor_cluster_gap_sec=args.anchor_cluster_gap_sec,
        family_match_tolerance_sec=args.family_match_tolerance_sec,
    )


def main() -> None:
    args = parse_args()
    dataset_root = args.output_root.resolve()
    aligned_csv = args.aligned_csv.resolve() if args.aligned_csv is not None else dataset_root / "benchmark_input_aligned.csv"

    alignment_payload: dict[str, object]
    if args.skip_alignment:
        alignment_payload = {
            "status": "skipped",
            "aligned_csv": str(aligned_csv),
            "manifest_path": str(dataset_root / "manifest.json"),
            "notes": ["Benchmark alignment was skipped and an existing aligned CSV is expected to already exist."],
        }
    else:
        alignment_result = run_alignment(config=build_alignment_config(args), limit=args.limit)
        aligned_csv = alignment_result.csv_path.resolve()
        alignment_payload = {
            "status": "completed",
            "aligned_csv": str(alignment_result.csv_path),
            "manifest_path": str(alignment_result.manifest_path),
            "row_count": int(alignment_result.row_count),
            "input_root": str(alignment_result.input_root),
            "output_root": str(alignment_result.output_root),
        }

    single_window_requested = list(args.single_window_experiments or SINGLE_WINDOW_EXPERIMENTS)
    multi_window_requested = list(args.multi_window_experiments or MULTI_WINDOW_EXPERIMENTS)

    real_labeling_payload: dict[str, object]
    labeled_csv = dataset_root / "benchmark_input_labeled.csv"
    labeling_report_path = dataset_root / "benchmark_labeling_report.json"
    if args.skip_real_labeling:
        real_labeling_payload = {
            "status": "skipped",
            "output_csv": str(labeled_csv),
            "report_path": str(labeling_report_path),
            "notes": ["Real labeling was skipped."],
        }
        feature_input_csv = aligned_csv
    else:
        label_result = build_real_event_labels(
            aligned_csv=aligned_csv,
            output_csv=labeled_csv,
        )
        real_labeling_payload = {
            "status": "completed",
            "aligned_csv": str(label_result.aligned_csv),
            "output_csv": str(label_result.output_csv),
            "report_path": str(label_result.report_path),
            "row_count": int(label_result.row_count),
            "lookup_matched_rows": int(label_result.lookup_matched_rows),
            "big_label_counts": dict(label_result.big_label_counts),
            "event_counts": dict(label_result.event_counts),
        }
        feature_input_csv = labeled_csv

    single_window_payload: dict[str, object]
    single_window_report_path = dataset_root / "single_window_feature_build_report.json"
    if args.skip_single_window_features:
        single_window_payload = {
            "status": "skipped",
            "report_path": str(single_window_report_path),
            "notes": ["Single-window feature exports were skipped."],
        }
    else:
        single_window_results = build_single_window_experiments(
            input_csv=feature_input_csv,
            output_dir=dataset_root,
            experiment_names=single_window_requested,
        )
        single_window_payload = build_stage_report(
            stage_name="single_window_feature_builder",
            input_csv=feature_input_csv,
            output_dir=dataset_root,
            requested_names=single_window_requested,
            results=single_window_results,
            notes=[
                "Single-window feature exports retain only big_label in addition to the feature contract when labels are available.",
                "This stage does not create labels by itself.",
            ],
        )
        write_report(single_window_report_path, single_window_payload)
        single_window_payload["status"] = "completed"
        single_window_payload["report_path"] = str(single_window_report_path)

    multi_window_payload: dict[str, object]
    multi_window_report_path = dataset_root / "multi_window_feature_build_report.json"
    if args.skip_multi_window_features:
        multi_window_payload = {
            "status": "skipped",
            "report_path": str(multi_window_report_path),
            "notes": ["Multi-window feature exports were skipped."],
        }
    else:
        multi_window_results = build_multi_window_experiments(
            input_csv=feature_input_csv,
            output_dir=dataset_root,
            experiment_names=multi_window_requested,
        )
        multi_window_payload = build_stage_report(
            stage_name="multi_window_feature_builder",
            input_csv=feature_input_csv,
            output_dir=dataset_root,
            requested_names=multi_window_requested,
            results=multi_window_results,
            notes=[
                "Multi-window feature exports retain only big_label in addition to the feature contract when labels are available.",
                "This stage does not create labels by itself.",
            ],
        )
        write_report(multi_window_report_path, multi_window_payload)
        multi_window_payload["status"] = "completed"
        multi_window_payload["report_path"] = str(multi_window_report_path)

    report_path = dataset_root / "benchmark_dataset_build_report.json"
    root_payload = {
        "generated_at_utc": utc_now_iso(),
        "pipeline": "benchmark_dataset_builder",
        "dataset_root": str(dataset_root),
        "aligned_csv": str(aligned_csv),
        "stages": {
            "alignment": alignment_payload,
            "real_labeling": real_labeling_payload,
            "single_window_features": single_window_payload,
            "multi_window_features": multi_window_payload,
        },
        "notes": [
            "The current benchmark_dataset tree owns benchmark dataset preparation and real-data rule labeling used downstream.",
            "benchmark_input_labeled.csv is rebuilt from benchmark_input_aligned.csv plus Layer0 Firebase metadata keyed by timestamp.",
        ],
    }
    write_report(report_path, root_payload)

    print("Benchmark dataset build complete")
    print(f"Dataset root: {dataset_root}")
    print(f"Aligned CSV: {aligned_csv}")
    print(f"Alignment status: {alignment_payload['status']}")
    print(f"Real labeling status: {real_labeling_payload['status']}")
    print(f"Single-window features status: {single_window_payload['status']}")
    print(f"Multi-window features status: {multi_window_payload['status']}")
    print(f"Build report: {report_path}")


if __name__ == "__main__":
    main()
