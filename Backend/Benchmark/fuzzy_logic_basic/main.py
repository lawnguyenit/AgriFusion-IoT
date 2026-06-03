from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.layer1.config import AlignmentConfig, default_input_root, default_output_root
from Backend.Benchmark.fuzzy_logic_basic.layer1.main import run_alignment
from Backend.Benchmark.fuzzy_logic_basic.layer2.src.pipeline import build_layer2_experiments
from Backend.Benchmark.fuzzy_logic_basic.layer3_combo.src.pipeline import build_layer3_combo_experiments
from Backend.Benchmark.fuzzy_logic_basic.real_event_labeling.src.pipeline import build_real_event_labels
from Backend.Benchmark.fuzzy_logic_basic.reporting import build_stage_report, utc_now_iso, write_report


LAYER2_EXPERIMENTS = ("exp1", "exp2", "exp3", "exp4", "exp5", "exp6")
LAYER3_COMBO_EXPERIMENTS = ("combo1", "combo2", "combo3", "combo4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the current FLB benchmark dataset package from Layer1 histories."
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
        help="Reuse an existing flb_input_aligned.csv. Only valid with --skip-layer1.",
    )
    parser.add_argument("--skip-layer1", action="store_true", help="Reuse an existing aligned CSV and skip Layer1 rebuild.")
    parser.add_argument(
        "--skip-real-event-labeling",
        action="store_true",
        help="Skip rebuilding flb_input_with_events.csv from Layer0 Firebase metadata.",
    )
    parser.add_argument("--skip-layer2", action="store_true", help="Skip Layer2 ablation exports.")
    parser.add_argument("--skip-layer3-combo", action="store_true", help="Skip Layer3 combo exports.")
    parser.add_argument(
        "--layer2-experiments",
        nargs="+",
        choices=LAYER2_EXPERIMENTS,
        default=None,
        help="Optional subset of Layer2 exports to generate.",
    )
    parser.add_argument(
        "--layer3-combo-experiments",
        nargs="+",
        choices=LAYER3_COMBO_EXPERIMENTS,
        default=None,
        help="Optional subset of Layer3 combo exports to generate.",
    )
    args = parser.parse_args()
    validate_args(args, parser)
    return args


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.aligned_csv is not None and not args.skip_layer1:
        parser.error("--aligned-csv is only valid with --skip-layer1.")
    if args.skip_layer1 and args.limit is not None:
        parser.error("--limit can only be used when Layer1 is rebuilt.")
    if args.skip_layer1 and args.anchor_cluster_gap_sec != 300:
        parser.error("--anchor-cluster-gap-sec can only be used when Layer1 is rebuilt.")
    if args.skip_layer1 and args.family_match_tolerance_sec != 1200:
        parser.error("--family-match-tolerance-sec can only be used when Layer1 is rebuilt.")
    if args.skip_layer1 and args.skip_real_event_labeling and args.skip_layer2 and args.skip_layer3_combo:
        parser.error("Nothing to build. Enable at least one stage or remove --skip-layer1.")


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
    aligned_csv = (args.aligned_csv.resolve() if args.aligned_csv is not None else dataset_root / "flb_input_aligned.csv")

    layer1_payload: dict[str, object]
    if args.skip_layer1:
        layer1_payload = {
            "status": "skipped",
            "aligned_csv": str(aligned_csv),
            "manifest_path": str(dataset_root / "manifest.json"),
            "notes": ["Layer1 was skipped and an existing aligned CSV is expected to already exist."],
        }
    else:
        layer1_result = run_alignment(config=build_alignment_config(args), limit=args.limit)
        aligned_csv = layer1_result.csv_path.resolve()
        layer1_payload = {
            "status": "completed",
            "aligned_csv": str(layer1_result.csv_path),
            "manifest_path": str(layer1_result.manifest_path),
            "row_count": int(layer1_result.row_count),
            "input_root": str(layer1_result.input_root),
            "output_root": str(layer1_result.output_root),
        }

    layer2_requested = list(args.layer2_experiments or LAYER2_EXPERIMENTS)
    layer3_combo_requested = list(args.layer3_combo_experiments or LAYER3_COMBO_EXPERIMENTS)

    real_event_payload: dict[str, object]
    labeled_csv = dataset_root / "flb_input_with_events.csv"
    labeling_report_path = dataset_root / "flb_real_event_labeling_report.json"
    if args.skip_real_event_labeling:
        real_event_payload = {
            "status": "skipped",
            "output_csv": str(labeled_csv),
            "report_path": str(labeling_report_path),
            "notes": ["Real event labeling was skipped."],
        }
        layer_feature_input_csv = aligned_csv
    else:
        label_result = build_real_event_labels(
            aligned_csv=aligned_csv,
            output_csv=labeled_csv,
        )
        real_event_payload = {
            "status": "completed",
            "aligned_csv": str(label_result.aligned_csv),
            "output_csv": str(label_result.output_csv),
            "report_path": str(label_result.report_path),
            "row_count": int(label_result.row_count),
            "lookup_matched_rows": int(label_result.lookup_matched_rows),
            "big_label_counts": dict(label_result.big_label_counts),
            "event_counts": dict(label_result.event_counts),
        }
        layer_feature_input_csv = labeled_csv

    layer2_payload: dict[str, object]
    layer2_report_path = dataset_root / "flb_layer2_build_report.json"
    if args.skip_layer2:
        layer2_payload = {
            "status": "skipped",
            "report_path": str(layer2_report_path),
            "notes": ["Layer2 ablation exports were skipped."],
        }
    else:
        layer2_results = build_layer2_experiments(
            input_csv=layer_feature_input_csv,
            output_dir=dataset_root,
            experiment_names=layer2_requested,
        )
        layer2_payload = build_stage_report(
            stage_name="layer2_dataset_builder",
            input_csv=layer_feature_input_csv,
            output_dir=dataset_root,
            requested_names=layer2_requested,
            results=layer2_results,
            notes=[
                "Layer2 builds train-facing exports and retains only big_label in addition to the feature contract when labels are available.",
                "This stage does not create labels by itself.",
            ],
        )
        write_report(layer2_report_path, layer2_payload)
        layer2_payload["status"] = "completed"
        layer2_payload["report_path"] = str(layer2_report_path)

    layer3_combo_payload: dict[str, object]
    layer3_combo_report_path = dataset_root / "flb_layer3_combo_build_report.json"
    if args.skip_layer3_combo:
        layer3_combo_payload = {
            "status": "skipped",
            "report_path": str(layer3_combo_report_path),
            "notes": ["Layer3 combo exports were skipped."],
        }
    else:
        layer3_combo_results = build_layer3_combo_experiments(
            input_csv=layer_feature_input_csv,
            output_dir=dataset_root,
            experiment_names=layer3_combo_requested,
        )
        layer3_combo_payload = build_stage_report(
            stage_name="layer3_combo_dataset_builder",
            input_csv=layer_feature_input_csv,
            output_dir=dataset_root,
            requested_names=layer3_combo_requested,
            results=layer3_combo_results,
            notes=[
                "Layer3 combo builds train-facing exports and retains only big_label in addition to the feature contract when labels are available.",
                "This stage does not create labels by itself.",
            ],
        )
        write_report(layer3_combo_report_path, layer3_combo_payload)
        layer3_combo_payload["status"] = "completed"
        layer3_combo_payload["report_path"] = str(layer3_combo_report_path)

    report_path = dataset_root / "flb_dataset_build_report.json"
    root_payload = {
        "generated_at_utc": utc_now_iso(),
        "pipeline": "flb_dataset_builder",
        "dataset_root": str(dataset_root),
        "aligned_csv": str(aligned_csv),
        "stages": {
            "layer1": layer1_payload,
            "real_event_labeling": real_event_payload,
            "layer2": layer2_payload,
            "layer3_combo": layer3_combo_payload,
        },
        "notes": [
            "The current fuzzy_logic_basic tree owns benchmark dataset preparation and real-data rule labeling used downstream.",
            "flb_input_with_events.csv is rebuilt from flb_input_aligned.csv plus Layer0 Firebase metadata keyed by timestamp.",
        ],
    }
    write_report(report_path, root_payload)

    print("FLB benchmark dataset build complete")
    print(f"Dataset root: {dataset_root}")
    print(f"Aligned CSV: {aligned_csv}")
    print(f"Layer1 status: {layer1_payload['status']}")
    print(f"Real event labeling status: {real_event_payload['status']}")
    print(f"Layer2 status: {layer2_payload['status']}")
    print(f"Layer3 combo status: {layer3_combo_payload['status']}")
    print(f"Build report: {report_path}")


if __name__ == "__main__":
    main()
