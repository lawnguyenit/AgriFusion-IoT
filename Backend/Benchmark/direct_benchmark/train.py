from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.direct_benchmark.src.config.settings import (
    DirectBenchmarkTrainConfig,
    default_dataset_output_root,
)
from Backend.Benchmark.direct_benchmark.src.pipeline.train_pipeline import run_training_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the unified 3-model suite from a prepared direct benchmark build run."
    )
    parser.add_argument(
        "--build-run-dir",
        type=Path,
        default=None,
        help="Prepared direct benchmark build run directory. Defaults to the latest run for the selected label lane.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("binary", "tri_class", "four_class"),
        required=True,
        help="Fixed label lane to train.",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=("v0", "v1", "v2", "v3", "v4", "v5"),
        default=None,
        help="Subset of direct experiments to train.",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        choices=("xgboost", "tabnet_classifier", "ft_transformer_classifier"),
        default=None,
        help="Optional subset of the unified 3-model suite.",
    )
    parser.add_argument("--output-root", type=Path, default=None, help="Optional training output root.")
    parser.add_argument("--smoke-test", action="store_true", help="Use a shorter run for quick validation.")
    return parser.parse_args()


def _latest_build_run_dir(label_mode: str) -> Path:
    root = default_dataset_output_root(label_mode)
    if not root.exists():
        raise FileNotFoundError(f"Dataset build root not found: {root}")
    candidates = [path.parent for path in root.rglob("dataset_manifest.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No prepared build runs found under: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> None:
    args = parse_args()
    config = DirectBenchmarkTrainConfig(label_mode=args.label_mode)
    config.build_run_dir = args.build_run_dir.resolve() if args.build_run_dir is not None else _latest_build_run_dir(args.label_mode)
    if args.experiments is not None:
        config.experiments = list(args.experiments)
    if args.model_names is not None:
        config.model_names = list(args.model_names)
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
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

    report = run_training_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Label mode: {report['label_mode']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
