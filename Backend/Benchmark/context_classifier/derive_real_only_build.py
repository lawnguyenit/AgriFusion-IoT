from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.config.train_settings import ContextTrainConfig
from Backend.Benchmark.context_classifier.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_classifier.src.pipeline.real_only_build_pipeline import run_real_only_build_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive a real-only context_classifier build run from an existing augmented build run."
    )
    parser.add_argument(
        "--source-build-run-dir",
        type=Path,
        default=None,
        help="Augmented build run dir to strip synthetic data from. Defaults to the latest build run for the label scheme.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root for derived real-only build artifacts. Defaults to outputs_real_only/<label_scheme>.",
    )
    parser.add_argument(
        "--label-scheme",
        choices=tuple(sorted(LABEL_SCHEMES)),
        default="four_class",
        help="Label scheme used to resolve the latest source build run when one is not supplied.",
    )
    return parser.parse_args()


def _resolve_source_build_run_dir(args: argparse.Namespace) -> Path:
    if args.source_build_run_dir is not None:
        return args.source_build_run_dir.resolve()
    config = ContextTrainConfig(label_scheme=args.label_scheme)
    config.resolve_defaults()
    if config.build_run_dir is None:
        raise FileNotFoundError(f"Could not resolve latest source build run for label_scheme={args.label_scheme}")
    return config.build_run_dir.resolve()


def main() -> None:
    args = parse_args()
    source_build_run_dir = _resolve_source_build_run_dir(args)
    report = run_real_only_build_pipeline(
        source_build_run_dir=source_build_run_dir,
        output_root=args.output_root.resolve() if args.output_root is not None else None,
    )
    print(f"Source build run: {report['source_build_run_dir']}")
    print(f"Label scheme: {report['label_scheme']}")
    print(f"Canonical rows: {report['canonical_row_count']}")
    print(f"Sequence rows (legacy export): {report['sequence_row_count']}")
    print(f"Real-only build output: {report['output_dir']}")


if __name__ == "__main__":
    main()
