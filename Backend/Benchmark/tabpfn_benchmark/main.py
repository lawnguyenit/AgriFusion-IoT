from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.tabpfn_benchmark.src.config.settings import TabPFNBenchmarkConfig
from Backend.Benchmark.tabpfn_benchmark.src.pipeline.train_pipeline import run_tabpfn_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train TabPFN downstream models on raw benchmark features without embedding pretraining."
    )
    parser.add_argument("--aligned-csv", type=Path, default=None, help="Path to flb_input_aligned.csv.")
    parser.add_argument("--event-csv", type=Path, default=None, help="Path to flb_input_with_events.csv.")
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
            "tabpfn_classifier",
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
    parser.add_argument(
        "--tabpfn-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Preferred device for TabPFN if the installed version supports device selection.",
    )
    parser.add_argument(
        "--tabpfn-model-path",
        type=str,
        default="tabpfn-v2-classifier-v2_default.ckpt",
        help="Model path or checkpoint name passed to TabPFN. Default forces the ungated v2 classifier checkpoint.",
    )
    parser.add_argument(
        "--tabpfn-fit-mode",
        choices=("fit_preprocessors", "low_memory", "batched"),
        default="fit_preprocessors",
        help="Best-effort fit mode passed to TabPFN when supported by the installed version.",
    )
    parser.add_argument(
        "--tabpfn-inference-config",
        choices=("auto", "low_memory", "fast"),
        default="auto",
        help="Best-effort inference preset passed to TabPFN when supported by the installed version.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Keep CLI parity with FT benchmark. No train shortening is needed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = TabPFNBenchmarkConfig()
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
    config.tabpfn_model_path = args.tabpfn_model_path
    config.tabpfn_device = args.tabpfn_device
    config.tabpfn_fit_mode = args.tabpfn_fit_mode
    config.tabpfn_inference_config = args.tabpfn_inference_config

    report = run_tabpfn_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Experiments: {', '.join(report['experiments'])}")
    print(f"Best experiment/model: {report['best_result']['experiment_name']} / {report['best_result']['model_name']}")
    print(f"Best validation macro_f1: {report['best_result']['validation_macro_f1']:.4f}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
