from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.reports.report_pipeline import (
    TrainingRunSpec,
    run_report_pipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate academic comparison charts and summary tables for context-classifier training runs."
    )
    parser.add_argument(
        "--five-class-run-dir",
        type=Path,
        required=True,
        help="Training run directory for the original five_class_v1 benchmark.",
    )
    parser.add_argument(
        "--option2-run-dir",
        type=Path,
        required=True,
        help="Training run directory for the Option 2 4-class benchmark.",
    )
    parser.add_argument(
        "--option2-sequence-run-dir",
        type=Path,
        default=None,
        help="Optional sequence-only training run for Option 2 if it was trained separately.",
    )
    parser.add_argument(
        "--five-class-sequence-run-dir",
        type=Path,
        default=None,
        help="Optional sequence-only training run for five_class_v1 if it was trained separately.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_specs = [
        TrainingRunSpec(label_scheme="five_class_v1", run_dir=args.five_class_run_dir.resolve()),
        TrainingRunSpec(label_scheme="option2_4class", run_dir=args.option2_run_dir.resolve()),
    ]
    if args.five_class_sequence_run_dir is not None:
        run_specs.append(
            TrainingRunSpec(label_scheme="five_class_v1", run_dir=args.five_class_sequence_run_dir.resolve())
        )
    if args.option2_sequence_run_dir is not None:
        run_specs.append(
            TrainingRunSpec(label_scheme="option2_4class", run_dir=args.option2_sequence_run_dir.resolve())
        )

    report = run_report_pipeline(run_specs=run_specs)
    print(f"Report run: {report['run_id']}")
    print(f"Output folder: {report['output_dir']}")
    print(f"Summary metrics: {report['summary_metrics_path']}")
    print(f"Markdown summary: {report['report_summary_path']}")


if __name__ == "__main__":
    main()
