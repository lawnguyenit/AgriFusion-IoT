from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_classifier.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_classifier.src.pipeline.train_pipeline import run_training_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train context-classifier tabular models on split-aware real+synthetic benchmark datasets."
    )
    parser.add_argument(
        "--build-run-dir",
        type=Path,
        default=None,
        help="Path to a built context_classifier dataset run. Defaults to the latest build run.",
    )
    parser.add_argument(
        "--experiment-names",
        nargs="+",
        choices=("v0", "v1", "v2", "v3"),
        default=None,
        help="Subset of experiments to train. Defaults to the full tabular ladder.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("xgboost", "tabnet_classifier", "ft_transformer_classifier"),
        default=None,
        help="Subset of models to train. Defaults to the full 3-model active suite.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional training output root. Defaults to the context_classifier artifacts/training root.",
    )
    parser.add_argument(
        "--label-scheme",
        choices=tuple(sorted(LABEL_SCHEMES)),
        default="four_class",
        help="Training label scheme. Defaults to the active 4-class contract and must match the build run directory.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run a shorter training smoke test.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ContextTrainConfig(label_scheme=args.label_scheme)
    if args.build_run_dir is not None:
        config.build_run_dir = args.build_run_dir.resolve()
    if args.experiment_names is not None:
        config.experiment_names = list(args.experiment_names)
    if args.model_names is not None:
        config.model_names = list(args.model_names)
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
    if args.smoke_test:
        if args.experiment_names is None:
            config.experiment_names = ["v0"]
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

    report = run_training_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Label scheme: {report['label_scheme']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
