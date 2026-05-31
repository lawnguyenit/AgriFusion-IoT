from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.direct_benchmark.src.config.settings import DirectBenchmarkConfig
from Backend.Benchmark.direct_benchmark.src.pipeline.train_pipeline import run_direct_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train direct downstream models on raw benchmark features without embedding pretraining."
    )
    parser.add_argument(
        "--aligned-csv",
        type=Path,
        default=None,
        help="Path to flb_input_aligned.csv. Defaults to the benchmark dataset CSV.",
    )
    parser.add_argument(
        "--event-csv",
        type=Path,
        default=None,
        help="Path to the event-annotated CSV. Defaults to flb_input_with_events.csv.",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        default=None,
        help="Subset of direct experiments to benchmark. Defaults to the full matched ladder.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("linear_probe", "random_forest", "hist_gradient_boosting", "torch_probe", "tabnet_classifier", "xgboost", "lightgbm"),
        default=None,
        help="Optional subset of downstream models to run. Defaults to a compact 3-model suite.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root. Defaults to Backend/Benchmark/direct_benchmark/outputs.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("auto", "binary", "ternary"),
        default="auto",
        help="Choose the downstream label scheme.",
    )
    parser.add_argument(
        "--split-strategy",
        choices=("chronological_v1", "chronological_with_lookback_gap"),
        default="chronological_with_lookback_gap",
        help="Split strategy used to create train/validation/test.",
    )
    parser.add_argument(
        "--split-gap-minutes",
        type=int,
        default=None,
        help="Optional explicit purge-gap override in minutes. Example: 1440 for 24h.",
    )
    parser.add_argument(
        "--min-class-support",
        type=int,
        default=20,
        help="Minimum support required for each ternary class when label-mode is auto.",
    )
    parser.add_argument(
        "--min-class-ratio",
        type=float,
        default=0.10,
        help="Minimum minority-to-majority ratio required for ternary mode when label-mode is auto.",
    )
    parser.add_argument("--max-epochs", type=int, default=120, help="Max epochs for the torch probe.")
    parser.add_argument("--patience", type=int, default=16, help="Early stopping patience for the torch probe.")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size for the torch probe.")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Learning rate for the torch probe.")
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
    config.max_epochs = 6 if args.smoke_test else args.max_epochs
    config.patience = 3 if args.smoke_test else args.patience
    config.batch_size = 32 if args.smoke_test else args.batch_size
    config.learning_rate = args.learning_rate
    if args.smoke_test:
        config.tabnet_max_epochs = 4
        config.tabnet_patience = 2
        config.tabnet_batch_size = 128
        config.tabnet_virtual_batch_size = 32
        config.tabnet_learning_rate = 5e-4

    report = run_direct_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
