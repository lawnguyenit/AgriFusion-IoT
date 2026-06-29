from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_benchmark.src.config.settings import CONTEXT_BENCHMARK_ROOT
from Backend.Benchmark.context_benchmark.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_benchmark.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_benchmark.src.pipeline.real_only_build_pipeline import run_real_only_build_pipeline
from Backend.Benchmark.context_benchmark.src.pipeline.train_pipeline import run_training_pipeline


DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3"]
DEFAULT_MODELS = ["xgboost", "tabnet_classifier", "ft_transformer_classifier"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive a real-only build run, then train the tabular context-benchmark models without synthetic augmentation."
    )
    parser.add_argument(
        "--source-build-run-dir",
        type=Path,
        default=None,
        help="Augmented build run dir to strip synthetic data from. Defaults to the latest build run for the label scheme.",
    )
    parser.add_argument(
        "--derived-build-run-dir",
        type=Path,
        default=None,
        help="Reuse an existing derived real-only build run. Skips the derive step when provided.",
    )
    parser.add_argument(
        "--label-scheme",
        choices=tuple(sorted(LABEL_SCHEMES)),
        default="four_class",
        help="Canonical label scheme for both derive and train steps.",
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
        help="Optional output root for derived real-only build artifacts. Defaults to artifacts/builds/<label_scheme>/real_only.",
    )
    parser.add_argument(
        "--train-output-root",
        type=Path,
        default=None,
        help="Optional output root for training artifacts. Defaults to artifacts/training/<label_scheme>/real_only.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run a fast validation pass.")
    return parser.parse_args()


def _default_real_only_build_root(label_scheme: str) -> Path:
    return (CONTEXT_BENCHMARK_ROOT / "artifacts" / "builds" / label_scheme / "real_only").resolve()


def _default_real_only_training_root(label_scheme: str) -> Path:
    return (CONTEXT_BENCHMARK_ROOT / "artifacts" / "training" / label_scheme / "real_only").resolve()


def _resolve_source_build_run_dir(label_scheme: str, source_build_run_dir: Path | None) -> Path:
    if source_build_run_dir is not None:
        return source_build_run_dir.resolve()
    config = ContextTrainConfig(label_scheme=label_scheme)
    config.resolve_defaults()
    if config.build_run_dir is None:
        raise FileNotFoundError(f"Could not resolve latest source build run for label_scheme={label_scheme}")
    return config.build_run_dir.resolve()


def _configure_train(args: argparse.Namespace, build_run_dir: Path) -> ContextTrainConfig:
    config = ContextTrainConfig(label_scheme=args.label_scheme)
    config.build_run_dir = build_run_dir.resolve()
    config.experiment_names = list(args.experiment_names or DEFAULT_EXPERIMENTS)
    config.model_names = list(args.model_names or DEFAULT_MODELS)
    config.output_root = (
        args.train_output_root.resolve()
        if args.train_output_root is not None
        else (
            args.build_output_root.resolve()
            if args.build_output_root is not None
            else _default_real_only_training_root(args.label_scheme)
        )
    )
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
    if args.derived_build_run_dir is None:
        source_build_run_dir = _resolve_source_build_run_dir(args.label_scheme, args.source_build_run_dir)
        build_report = run_real_only_build_pipeline(
            source_build_run_dir=source_build_run_dir,
            output_root=args.build_output_root.resolve() if args.build_output_root is not None else None,
        )
        build_run_dir = Path(build_report["output_dir"]).resolve()
        print(f"Source build run: {build_report['source_build_run_dir']}")
        print(f"Derived real-only build run: {build_run_dir}")
    else:
        build_run_dir = args.derived_build_run_dir.resolve()
        print(f"Reusing derived real-only build run: {build_run_dir}")

    train_config = _configure_train(args, build_run_dir)
    train_report = run_training_pipeline(train_config)
    print(f"Label scheme: {train_report['label_scheme']}")
    print(f"Experiments: {', '.join(train_report['experiments'])}")
    print(
        "Best experiment/model: "
        f"{train_report['best_result']['experiment_name']} / {train_report['best_result']['model_name']}"
    )
    print(f"Best validation macro_f1: {train_report['best_result']['validation_macro_f1']:.4f}")
    print(f"Real-only training output: {train_report['output_dir']}")


if __name__ == "__main__":
    main()
