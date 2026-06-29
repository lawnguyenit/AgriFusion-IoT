from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.tabular_benchmark.src.config.settings import DirectBenchmarkConfig
from Backend.Benchmark.tabular_benchmark.src.pipeline.train_pipeline import run_direct_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convenience wrapper: build a real-only dataset lane then train the unified tabular benchmark suite."
    )
    parser.add_argument("--aligned-csv", type=Path, default=None, help="Path to benchmark_input_aligned.csv.")
    parser.add_argument("--event-csv", type=Path, default=None, help="Path to benchmark_input_labeled.csv.")
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        default=None,
        help="Subset of direct experiments to benchmark.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("xgboost", "tabnet_classifier", "ft_transformer_classifier"),
        default=None,
        help="Optional subset of the unified 3-model suite.",
    )
    parser.add_argument("--output-root", type=Path, default=None, help="Optional training output root.")
    parser.add_argument(
        "--label-mode",
        choices=("auto", "binary", "tri_class", "four_class"),
        default="auto",
        help="Choose the active label ladder level for direct training.",
    )
    parser.add_argument(
        "--split-strategy",
        choices=("chronological_v1", "chronological_with_lookback_gap", "coverage_aware_temporal"),
        default="coverage_aware_temporal",
        help="Split strategy used to create train/validation/test.",
    )
    parser.add_argument("--split-gap-minutes", type=int, default=None, help="Optional explicit purge-gap override in minutes.")
    parser.add_argument("--min-class-support", type=int, default=20, help="Minimum class support required in auto mode.")
    parser.add_argument("--min-class-ratio", type=float, default=0.10, help="Minimum minority-to-majority ratio required in auto mode.")
    parser.add_argument("--smoke-test", action="store_true", help="Use a shorter run for quick validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DirectBenchmarkConfig()
    if args.aligned_csv is not None:
        config.aligned_csv = args.aligned_csv.resolve()
    if args.event_csv is not None:
        config.event_csv = args.event_csv.resolve()
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
    if args.experiments is not None:
        config.experiments = list(args.experiments)
    if args.model_names is not None:
        config.model_names = list(args.model_names)
    config.label_mode = args.label_mode
    config.split_strategy = args.split_strategy
    config.split_gap_minutes_override = args.split_gap_minutes
    config.min_class_support = args.min_class_support
    config.min_class_ratio = args.min_class_ratio
    if args.smoke_test:
        config.tabnet_max_epochs = 4
        config.tabnet_patience = 2
        config.tabnet_batch_size = 32
        config.tabnet_virtual_batch_size = 16
        config.ft_max_epochs = 6
        config.ft_patience = 3
        config.ft_batch_size = 32
        config.ft_model_dim = 32
        config.ft_token_dim = 32
        config.ft_num_heads = 4
        config.ft_num_layers = 2

    report = run_direct_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Label mode: {report['label_mode']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
