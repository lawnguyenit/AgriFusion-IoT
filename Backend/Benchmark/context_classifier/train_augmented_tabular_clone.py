from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.config.settings import CONTEXT_CLASSIFIER_ROOT, ContextClassifierConfig
from Backend.Benchmark.context_classifier.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_classifier.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_classifier.src.pipeline.build_pipeline import run_build_pipeline
from Backend.Benchmark.context_classifier.src.pipeline.train_pipeline import run_training_pipeline


DEFAULT_EXPERIMENTS = ["v0", "v1", "v2", "v3"]
DEFAULT_MODELS = ["xgboost", "tabnet_classifier", "ft_transformer_classifier"]
SIMULATOR_CLONE_ROOT = ROOT_DIR / "Backend" / "SimulatorClone"
SIMULATOR_CLONE_OUTPUTS_ROOT = SIMULATOR_CLONE_ROOT / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and train real+synthetic tabular benchmarks from Backend/SimulatorClone with isolated output roots."
    )
    parser.add_argument(
        "--build-run-dir",
        type=Path,
        default=None,
        help="Reuse an existing built context_classifier clone dataset run. Skips dataset build when provided.",
    )
    parser.add_argument(
        "--simulator-clone-run-dir",
        type=Path,
        default=None,
        help="Explicit SimulatorClone run dir. If omitted, uses the latest run under Backend/SimulatorClone/outputs.",
    )
    parser.add_argument(
        "--real-event-csv",
        type=Path,
        default=None,
        help="Path to flb_input_with_events.csv. Defaults to the fuzzy benchmark dataset export.",
    )
    parser.add_argument(
        "--synthetic-gap-aware-csv",
        type=Path,
        default=None,
        help="Path to synthetic_flb_gap_aware.csv. Overrides simulator-clone-run-dir when provided.",
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
        help="Optional output root for the dataset build stage. Defaults to context_classifier/artifacts/builds/<label_scheme>/clone.",
    )
    parser.add_argument(
        "--train-output-root",
        type=Path,
        default=None,
        help="Optional output root for the training stage. Defaults to context_classifier/artifacts/training/<label_scheme>/clone.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run a fast validation pass.")
    return parser.parse_args()


def _default_clone_build_root(label_scheme: str) -> Path:
    return (CONTEXT_CLASSIFIER_ROOT / "artifacts" / "builds" / label_scheme / "clone").resolve()


def _default_clone_training_root(label_scheme: str) -> Path:
    return (CONTEXT_CLASSIFIER_ROOT / "artifacts" / "training" / label_scheme / "clone").resolve()


def _latest_simulator_clone_run_dir() -> Path:
    outputs_root = SIMULATOR_CLONE_OUTPUTS_ROOT.resolve()
    if not outputs_root.exists():
        raise FileNotFoundError(f"SimulatorClone outputs root not found: {outputs_root}")
    candidates = [path for path in outputs_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No SimulatorClone run directories found under: {outputs_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _resolve_synthetic_gap_aware_csv(args: argparse.Namespace) -> Path:
    if args.synthetic_gap_aware_csv is not None:
        return args.synthetic_gap_aware_csv.resolve()
    run_dir = args.simulator_clone_run_dir.resolve() if args.simulator_clone_run_dir is not None else _latest_simulator_clone_run_dir()
    synthetic_csv = (run_dir / "synthetic_flb_gap_aware.csv").resolve()
    if not synthetic_csv.exists():
        raise FileNotFoundError(f"SimulatorClone gap-aware CSV not found: {synthetic_csv}")
    return synthetic_csv


def _configure_build(args: argparse.Namespace) -> ContextClassifierConfig:
    config = ContextClassifierConfig(label_scheme=args.label_scheme)
    if args.real_event_csv is not None:
        config.real_event_csv = args.real_event_csv.resolve()
    config.synthetic_gap_aware_csv = _resolve_synthetic_gap_aware_csv(args)
    config.output_root = (
        args.build_output_root.resolve()
        if args.build_output_root is not None
        else _default_clone_build_root(args.label_scheme)
    )
    if args.smoke_test:
        config.sequence_lookback = 6
    return config


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
            else _default_clone_training_root(args.label_scheme)
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
    synthetic_gap_aware_csv = _resolve_synthetic_gap_aware_csv(args)
    print(f"SimulatorClone synthetic source: {synthetic_gap_aware_csv}")

    if args.build_run_dir is None:
        build_config = _configure_build(args)
        build_report = run_build_pipeline(build_config)
        build_run_dir = Path(build_report["output_dir"]).resolve()
        print(f"Clone build run: {build_run_dir}")
    else:
        build_run_dir = args.build_run_dir.resolve()
        print(f"Reusing clone build run: {build_run_dir}")

    train_config = _configure_train(args, build_run_dir)
    train_report = run_training_pipeline(train_config)
    print(f"Label scheme: {train_report['label_scheme']}")
    print(f"Experiments: {', '.join(train_report['experiments'])}")
    print(
        "Best experiment/model: "
        f"{train_report['best_result']['experiment_name']} / {train_report['best_result']['model_name']}"
    )
    print(f"Best validation macro_f1: {train_report['best_result']['validation_macro_f1']:.4f}")
    print(f"Clone training output: {train_report['output_dir']}")


if __name__ == "__main__":
    main()
