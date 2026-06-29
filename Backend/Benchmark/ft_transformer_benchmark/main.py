from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.ft_transformer_benchmark.src.config.settings import FTTransformerBenchmarkConfig
from Backend.Benchmark.ft_transformer_benchmark.src.pipeline.train_pipeline import run_ft_transformer_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train FT-Transformer downstream models on raw benchmark features without embedding pretraining."
    )
    parser.add_argument("--aligned-csv", type=Path, default=None, help="Path to benchmark_input_aligned.csv.")
    parser.add_argument("--event-csv", type=Path, default=None, help="Path to benchmark_input_labeled.csv.")
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        default=None,
        help="Subset of raw-feature experiments to benchmark.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=(
            "linear_probe",
            "random_forest",
            "hist_gradient_boosting",
            "xgboost",
            "lightgbm",
            "ft_transformer_classifier",
        ),
        default=None,
        help="Optional subset of models to run.",
    )
    parser.add_argument("--output-root", type=Path, default=None, help="Optional output root.")
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
    parser.add_argument("--split-gap-minutes", type=int, default=None, help="Optional purge-gap override in minutes.")
    parser.add_argument("--min-class-support", type=int, default=20, help="Minimum support required in auto label mode.")
    parser.add_argument(
        "--min-class-ratio",
        type=float,
        default=0.10,
        help="Minimum minority-to-majority ratio required in auto label mode.",
    )
    parser.add_argument("--ft-max-epochs", type=int, default=140, help="Max epochs for FT-Transformer.")
    parser.add_argument("--ft-patience", type=int, default=18, help="Early stopping patience for FT-Transformer.")
    parser.add_argument("--ft-batch-size", type=int, default=64, help="Batch size for FT-Transformer.")
    parser.add_argument("--ft-learning-rate", type=float, default=8e-4, help="Learning rate for FT-Transformer.")
    parser.add_argument("--smoke-test", action="store_true", help="Use a shorter run for quick validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = FTTransformerBenchmarkConfig()
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
    config.ft_max_epochs = 6 if args.smoke_test else args.ft_max_epochs
    config.ft_patience = 3 if args.smoke_test else args.ft_patience
    config.ft_batch_size = 32 if args.smoke_test else args.ft_batch_size
    config.ft_learning_rate = args.ft_learning_rate
    if args.smoke_test:
        config.ft_model_dim = 32
        config.ft_token_dim = 32
        config.ft_num_heads = 4
        config.ft_num_layers = 2

    report = run_ft_transformer_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
