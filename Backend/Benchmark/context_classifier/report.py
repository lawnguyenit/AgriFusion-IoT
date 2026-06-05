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
        description="Generate comparison charts and summary tables for one or more context-classifier training runs."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        action="append",
        required=True,
        help="Training run directory to include in the report. Repeat this flag to compare multiple runs.",
    )
    parser.add_argument(
        "--label-scheme",
        action="append",
        default=None,
        help="Optional label scheme for each --run-dir. If omitted, four_class is assumed for every run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    label_schemes = list(args.label_scheme or [])
    if label_schemes and len(label_schemes) != len(args.run_dir):
        raise ValueError("When --label-scheme is provided, it must appear the same number of times as --run-dir.")

    run_specs: list[TrainingRunSpec] = []
    for index, run_dir in enumerate(args.run_dir):
        scheme = label_schemes[index] if label_schemes else "four_class"
        run_specs.append(TrainingRunSpec(label_scheme=scheme, run_dir=run_dir.resolve()))

    report = run_report_pipeline(run_specs=run_specs)
    print(f"Report run: {report['run_id']}")
    print(f"Output folder: {report['output_dir']}")
    print(f"Summary metrics: {report['summary_metrics_path']}")
    print(f"Markdown summary: {report['report_summary_path']}")


if __name__ == "__main__":
    main()
