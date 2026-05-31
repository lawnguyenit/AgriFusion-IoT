from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.config.settings import ContextClassifierConfig
from Backend.Benchmark.context_classifier.src.data.label_schemes import LABEL_SCHEMES
from Backend.Benchmark.context_classifier.src.pipeline.build_pipeline import run_build_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical real+synthetic context datasets for the context classifier benchmark."
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
        help="Path to synthetic_flb_gap_aware.csv. Defaults to the latest simulator run.",
    )
    parser.add_argument(
        "--synthetic-labeled-csv",
        type=Path,
        default=None,
        help="Path to synthetic_flb_input_labeled.csv. Defaults to the latest simulator run.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root. Defaults to Backend/Benchmark/context_classifier/outputs.",
    )
    parser.add_argument(
        "--label-scheme",
        choices=tuple(sorted(LABEL_SCHEMES)),
        default="five_class_v1",
        help="Canonical label scheme. Option 2 uses a separate output tree by default.",
    )
    parser.add_argument(
        "--sequence-lookback",
        type=int,
        default=12,
        help="Lookback length in steps for LSTM sequence dataset generation.",
    )
    parser.add_argument(
        "--sequence-stride",
        type=int,
        default=1,
        help="Stride in steps for sequence dataset generation.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Build smaller derived datasets for a quick validation pass.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ContextClassifierConfig(label_scheme=args.label_scheme)
    if args.real_event_csv is not None:
        config.real_event_csv = args.real_event_csv.resolve()
    if args.synthetic_gap_aware_csv is not None:
        config.synthetic_gap_aware_csv = args.synthetic_gap_aware_csv.resolve()
    if args.synthetic_labeled_csv is not None:
        config.synthetic_labeled_csv = args.synthetic_labeled_csv.resolve()
    if args.output_root is not None:
        config.output_root = args.output_root.resolve()
    config.sequence_lookback = args.sequence_lookback
    config.sequence_stride = args.sequence_stride
    if args.smoke_test:
        config.sequence_lookback = min(config.sequence_lookback, 6)

    report = run_build_pipeline(config)
    print(f"Benchmark family: {report['benchmark_family']}")
    print(f"Benchmark version: {report['benchmark_version']}")
    print(f"Label scheme: {report['label_scheme']}")
    print(f"Canonical rows: {report['canonical_row_count']}")
    print(f"Tabular outputs: {', '.join(report['tabular_outputs'].keys())}")
    print(f"Sequence rows: {report['sequence_row_count']}")
    print(f"Output folder: {report['output_dir']}")


if __name__ == "__main__":
    main()
