from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_benchmark.src.config.settings import ContextBenchmarkConfig
from Backend.Benchmark.context_benchmark.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_benchmark.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_benchmark.src.pipeline.build_pipeline import run_build_pipeline
from Backend.Benchmark.context_benchmark.src.pipeline.train_pipeline import run_training_pipeline


DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3"]
DEFAULT_MODELS = ["xgboost", "tabnet_classifier", "ft_transformer_classifier"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and train real+synthetic tabular benchmarks for XGBoost, TabNet, and FT-Transformer."
    )
    parser.add_argument(
        "--build-run-dir",
        type=Path,
        default=None,
        help="Reuse an existing built context_benchmark dataset run. Skips dataset build when provided.",
    )
    parser.add_argument(
        "--real-event-csv",
        type=Path,
        default=None,
        help="Path to benchmark_input_labeled.csv. Defaults to the active benchmark dataset export.",
    )
    parser.add_argument(
        "--synthetic-gap-aware-csv",
        type=Path,
        default=None,
        help="Path to synthetic_benchmark_gap_aware.csv. Defaults to the latest simulator run.",
    )
    parser.add_argument(
        "--label-scheme",
        choices=tuple(sorted(LABEL_SCHEMES)),
        default="four_class",
        help="Canonical label scheme for both build and train steps.",
    )
    parser.add_argument(
        "--experiment-names",
        nargs="+",
        choices=("v0", "v1", "v2", "v3"),
        default=None,
        help="Tabular experiments to train. Defaults to v0 v1 v2 v3.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("xgboost", "tabnet_classifier", "ft_transformer_classifier"),
        default=None,
        help="Tabular models to train. Defaults to XGBoost, TabNet, and FT-Transformer.",
    )
    parser.add_argument(
        "--build-output-root",
        type=Path,
        default=None,
        help="Optional output root for the dataset build stage.",
    )
    parser.add_argument(
        "--train-output-root",
        type=Path,
        default=None,
        help="Optional output root for the training stage.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run a fast validation pass.")
    return parser.parse_args()


def _configure_build(args: argparse.Namespace) -> ContextBenchmarkConfig:
    config = ContextBenchmarkConfig(label_scheme=args.label_scheme)
    if args.real_event_csv is not None:
        config.real_event_csv = args.real_event_csv.resolve()
    if args.synthetic_gap_aware_csv is not None:
        config.synthetic_gap_aware_csv = args.synthetic_gap_aware_csv.resolve()
    if args.build_output_root is not None:
        config.output_root = args.build_output_root.resolve()
    if args.smoke_test:
        config.sequence_lookback = 6
    return config


def _configure_train(args: argparse.Namespace, build_run_dir: Path) -> ContextTrainConfig:
    config = ContextTrainConfig(label_scheme=args.label_scheme)
    config.build_run_dir = build_run_dir.resolve()
    config.experiment_names = list(args.experiment_names or DEFAULT_EXPERIMENTS)
    config.model_names = list(args.model_names or DEFAULT_MODELS)
    if args.train_output_root is not None:
        config.output_root = args.train_output_root.resolve()
    if args.smoke_test:
        config.tabnet_max_epochs = 6
        config.tabnet_patience = 3
        config.tabnet_batch_size = 32
        config.tabnet_virtual_batch_size = 16
        config.ft_max_epochs = 6
        config.ft_patience = 3
        config.ft_batch_size = 32
        config.ft_model_dim = 32
        config.ft_token_dim = 32
        config.ft_num_heads = 4
        config.ft_num_layers = 2
    return config


def main() -> None:
    args = parse_args()

    if args.build_run_dir is None:
        build_config = _configure_build(args)
        build_report = run_build_pipeline(build_config)
        build_run_dir = Path(build_report["output_dir"]).resolve()
        print(f"Build run: {build_run_dir}")
    else:
        build_run_dir = args.build_run_dir.resolve()
        print(f"Reusing build run: {build_run_dir}")

    train_config = _configure_train(args, build_run_dir)
    train_report = run_training_pipeline(train_config)
    print(f"Label scheme: {train_report['label_scheme']}")
    print(f"Experiments: {', '.join(train_report['experiments'])}")
    print(f"Best experiment/model: {train_report['best_result']['experiment_name']} / {train_report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {train_report['best_result']['validation_macro_f1']:.4f}")
    print(f"Training output: {train_report['output_dir']}")


if __name__ == "__main__":
    main()
