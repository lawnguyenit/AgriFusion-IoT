from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.tabular_benchmark.src.config.settings import (
    default_training_output_root,
)
from Backend.Benchmark.tabular_benchmark.src.pipeline.report_pipeline import run_report_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate summary metrics and charts for a tabular benchmark training run."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Direct benchmark training run directory. Defaults to the latest run for the selected label lane.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("binary", "tri_class", "four_class"),
        required=True,
        help="Label lane to report.",
    )
    return parser.parse_args()


def _latest_training_run_dir(label_mode: str) -> Path:
    root = default_training_output_root(label_mode)
    if not root.exists():
        raise FileNotFoundError(f"Training root not found: {root}")
    candidates: list[Path] = []
    for path in root.rglob("training_report.json"):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and "experiment_reports" in payload and "best_result" in payload:
            candidates.append(path.parent)
    if not candidates:
        raise FileNotFoundError(f"No training runs found under: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve() if args.run_dir is not None else _latest_training_run_dir(args.label_mode)
    report = run_report_pipeline(training_run_dir=run_dir, label_mode=args.label_mode)
    print(f"Report run: {report['run_id']}")
    print(f"Label mode: {report['label_mode']}")
    print(f"Output folder: {report['output_dir']}")
    print(f"Summary metrics: {report['summary_metrics_path']}")
    print(f"Markdown summary: {report['report_summary_path']}")


if __name__ == "__main__":
    main()
