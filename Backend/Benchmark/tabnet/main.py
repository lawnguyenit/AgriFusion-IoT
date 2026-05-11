from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.tabnet.src.config.settings import PretrainConfig
from Backend.Benchmark.tabnet.src.config.source_registry import resolve_source_csv
from Backend.Benchmark.tabnet.src.pipeline.pretrain_pipeline import run_pretraining_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run self-supervised TabNet pretraining with masked feature reconstruction."
    )
    parser.add_argument(
        "--source-kind",
        choices=("layer1", "layer2", "layer3", "layer4", "layer5", "custom"),
        default="layer1",
        help="Benchmark source profile. Layer2-5 are reserved for future fuzzy outputs.",
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Optional override for the aligned FLB input CSV.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional override for the pretrain output root.",
    )
    parser.add_argument(
        "--include-npk-proxy",
        action="store_true",
        help="Add a derived EC/N/P/K proxy feature without using N, P, K as independent features.",
    )
    parser.add_argument(
        "--mask-ratio",
        type=float,
        default=0.2,
        help="Fraction of numerical features to mask per sample.",
    )
    parser.add_argument("--batch-size", type=int, default=256, help="Training batch size.")
    parser.add_argument(
        "--virtual-batch-size",
        type=int,
        default=128,
        help="Ghost batch size used inside TabNet blocks.",
    )
    parser.add_argument("--max-epochs", type=int, default=40, help="Maximum pretraining epochs.")
    parser.add_argument("--patience", type=int, default=8, help="Early stopping patience.")
    parser.add_argument("--learning-rate", type=float, default=2e-3, help="Optimizer learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-5, help="Optimizer weight decay.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--n-d", type=int, default=16, help="TabNet decision block width.")
    parser.add_argument("--n-a", type=int, default=16, help="TabNet attention block width.")
    parser.add_argument("--n-steps", type=int, default=4, help="Number of TabNet decision steps.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run a short smoke configuration without changing the default output contract.",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> PretrainConfig:
    config = PretrainConfig()
    config.source_kind = args.source_kind
    source_kind, resolved_input_csv = resolve_source_csv(
        source_kind=args.source_kind,
        input_csv=args.input_csv,
        root_dir=ROOT_DIR,
    )
    config.source_kind = source_kind
    config.input_csv = resolved_input_csv
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()

    config.include_npk_proxy = args.include_npk_proxy
    config.mask_ratio = args.mask_ratio
    config.batch_size = args.batch_size
    config.virtual_batch_size = args.virtual_batch_size
    config.max_epochs = args.max_epochs
    config.patience = args.patience
    config.learning_rate = args.learning_rate
    config.weight_decay = args.weight_decay
    config.seed = args.seed
    config.n_d = args.n_d
    config.n_a = args.n_a
    config.n_steps = args.n_steps

    if args.smoke_test:
        config.max_epochs = min(config.max_epochs, 3)
        config.patience = min(config.patience, 2)
        config.batch_size = min(config.batch_size, 128)
        config.virtual_batch_size = min(config.virtual_batch_size, 64)
        config.run_label = "smoke"

    return config


def main() -> None:
    args = parse_args()
    config = build_config(args)
    report = run_pretraining_pipeline(config)

    print("TabNet self-supervised pretraining complete")
    print(f"Run id: {report['run_id']}")
    print(f"Input CSV: {report['input_csv']}")
    print(f"Output dir: {report['output_dir']}")
    print(f"Rows before cleaning: {report['row_counts']['before_cleaning']}")
    print(f"Rows after cleaning: {report['row_counts']['after_cleaning']}")
    print(
        "Chronological split: "
        f"train={report['split_counts']['train']}, "
        f"validation={report['split_counts']['validation']}, "
        f"test={report['split_counts']['test']}"
    )
    print(f"Features: {', '.join(report['feature_columns'])}")
    print(f"Best validation masked MSE: {report['training']['best_validation_loss']:.6f}")
    print(f"Checkpoint: {report['artifacts']['checkpoint_path']}")


if __name__ == "__main__":
    main()
