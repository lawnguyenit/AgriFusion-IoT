from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.tabpfn_benchmark.src.reports.report_pipeline import (
    TrainingRunSpec,
    run_report_pipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate academic charts and summary tables for TabPFN benchmark runs."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        action="append",
        required=True,
        help="Training run directory under tabpfn_benchmark/outputs.",
    )
    parser.add_argument(
        "--run-label",
        action="append",
        default=None,
        help="Optional label for the corresponding --run-dir. If omitted, the run folder name is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dirs = [path.resolve() for path in args.run_dir]
    if args.run_label is not None and len(args.run_label) != len(run_dirs):
        raise ValueError("The number of --run-label values must match the number of --run-dir values.")

    run_specs: list[TrainingRunSpec] = []
    for index, run_dir in enumerate(run_dirs):
        run_label = args.run_label[index] if args.run_label is not None else run_dir.name
        run_specs.append(TrainingRunSpec(run_label=run_label, run_dir=run_dir))

    report = run_report_pipeline(run_specs=run_specs)
    print(f"Report run: {report['run_id']}")
    print(f"Output folder: {report['output_dir']}")
    print(f"Summary metrics: {report['summary_metrics_path']}")
    print(f"Markdown summary: {report['report_summary_path']}")


if __name__ == "__main__":
    main()
