from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.direct_benchmark.src.config.settings import DirectBenchmarkBuildConfig
from Backend.Benchmark.direct_benchmark.src.pipeline.build_pipeline import run_build_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build real-only tabular benchmark datasets for a fixed label lane."
    )
    parser.add_argument("--aligned-csv", type=Path, default=None, help="Path to flb_input_aligned.csv.")
    parser.add_argument("--event-csv", type=Path, default=None, help="Path to flb_input_with_events.csv.")
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        default=None,
        help="Subset of direct experiments to build.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("binary", "tri_class", "four_class"),
        required=True,
        help="Fixed label lane to build.",
    )
    parser.add_argument("--output-root", type=Path, default=None, help="Optional dataset build output root.")
    parser.add_argument(
        "--split-strategy",
        choices=("chronological_v1", "chronological_with_lookback_gap", "coverage_aware_temporal"),
        default="coverage_aware_temporal",
        help="Split strategy used to create train/validation/test.",
    )
    parser.add_argument("--split-gap-minutes", type=int, default=None, help="Optional explicit purge-gap override in minutes.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DirectBenchmarkBuildConfig(label_mode=args.label_mode)
    if args.aligned_csv is not None:
        config.aligned_csv = args.aligned_csv.resolve()
    if args.event_csv is not None:
        config.event_csv = args.event_csv.resolve()
    if args.experiments is not None:
        config.experiments = list(args.experiments)
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
    config.split_strategy = args.split_strategy
    config.split_gap_minutes_override = args.split_gap_minutes

    report = run_build_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Label mode: {report['label_mode']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
