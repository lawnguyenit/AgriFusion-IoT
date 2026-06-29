from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import BENCHMARK_DATASETS_ROOT
from Backend.Benchmark.benchmark_dataset.real_labeling.src.pipeline import build_real_event_labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the real-data event label artifact for benchmark_dataset from aligned Layer1 rows and Layer0 Firebase metadata."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=BENCHMARK_DATASETS_ROOT / "benchmark_input_aligned.csv",
        help="Aligned benchmark CSV used as the feature source of truth.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=BENCHMARK_DATASETS_ROOT / "benchmark_input_labeled.csv",
        help="Managed labeled benchmark CSV path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_real_event_labels(
        aligned_csv=args.input_csv,
        output_csv=args.output_csv,
    )
    print("Real event labeling complete")
    print(f"Aligned CSV: {result.aligned_csv}")
    print(f"Output CSV: {result.output_csv}")
    print(f"Rows: {result.row_count}")
    print(f"Lookup rows with raw metadata: {result.lookup_matched_rows}")
    print(f"Label counts: {result.big_label_counts}")
    print(f"Build report: {result.report_path}")


if __name__ == "__main__":
    main()
