from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.reporting import build_stage_report, write_report
from Backend.Benchmark.fuzzy_logic_basic.layer3_combo.src.pipeline import (
    Layer3ComboBuildResult,
    build_layer3_combo_experiments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Layer3 combo benchmark CSVs from the Layer1 aligned dataset."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Optional override for the Layer1 aligned CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional override for the dataset output folder.",
    )
    parser.add_argument(
        "--experiment",
        choices=("all", "combo1", "combo2", "combo3", "combo4"),
        default="all",
        help="Which combo dataset to emit.",
    )
    return parser.parse_args()


def _print_result(result: Layer3ComboBuildResult) -> None:
    print(f"Experiment: {result.experiment_name}")
    print(f"Input CSV: {result.input_csv}")
    print(f"Output CSV: {result.output_csv}")
    print(f"Rows: {result.row_count}")
    print(f"Columns: {len(result.columns)}")


def main() -> None:
    args = parse_args()
    experiment_names = None if args.experiment == "all" else [args.experiment]
    results = build_layer3_combo_experiments(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        experiment_names=experiment_names,
    )
    requested_names = list(experiment_names or ["combo1", "combo2", "combo3", "combo4"])
    report_payload = build_stage_report(
        stage_name="layer3_combo_dataset_builder",
        input_csv=results[0].input_csv,
        output_dir=results[0].output_csv.parent,
        requested_names=requested_names,
        results=results,
        notes=[
            "Layer3 combo builds multi-window train-facing exports from the current FLB dataset source.",
            "This stage does not generate labels and only retains big_label when it is already present.",
        ],
    )
    report_path = results[0].output_csv.parent / "flb_layer3_combo_build_report.json"
    write_report(report_path, report_payload)
    print("Layer3 combo datasets complete")
    for result in results:
        _print_result(result)
    print(f"Build report: {report_path}")


if __name__ == "__main__":
    main()
