from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.pretrain_supervised.v0.src.config.settings import V0Config
from Backend.Benchmark.pretrain_supervised.v0.src.pipeline.train_pipeline import run_v0_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train downstream v0 models on embeddings produced from the nutrient/pH ablation benchmark."
    )
    parser.add_argument(
        "--event-csv",
        type=Path,
        default=None,
        help="Path to the real labeled CSV. Defaults to benchmark_input_labeled.csv.",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("ph", "npk", "ph_npk"),
        default=None,
        help="Subset of Layer0 experiments to benchmark. Defaults to all ablations.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root. Defaults to Backend/Benchmark/pretrain_supervised/v0/outputs.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("auto", "binary", "ternary"),
        default="auto",
        help="Choose the downstream label scheme.",
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
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("linear_probe", "random_forest", "hist_gradient_boosting", "xgboost", "lightgbm"),
        default=None,
        help="Optional sklearn suite override. Torch probe is always trained separately.",
    )
    parser.add_argument("--max-epochs", type=int, default=100, help="Max epochs for the torch probe.")
    parser.add_argument("--patience", type=int, default=8, help="Early stopping patience for the torch probe.")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size for the torch probe.")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Learning rate for the torch probe.")
    parser.add_argument("--smoke-test", action="store_true", help="Use a shorter run for quick validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = V0Config()
    if args.event_csv is not None:
        config.event_csv = args.event_csv.resolve()
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
    if args.experiments is not None:
        config.experiments = list(args.experiments)
    if args.model_names is not None:
        config.model_names = list(args.model_names)
    config.label_mode = args.label_mode
    config.min_class_support = args.min_class_support
    config.min_class_ratio = args.min_class_ratio
    config.max_epochs = 6 if args.smoke_test else args.max_epochs
    config.patience = 3 if args.smoke_test else args.patience
    config.batch_size = 32 if args.smoke_test else args.batch_size
    config.learning_rate = args.learning_rate

    report = run_v0_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
