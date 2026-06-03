from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.context_classifier.src.pipeline.scientific_artifact_pipeline import (
    backfill_training_run_scientific_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate prediction-level and scientific artifacts for an existing context-classifier training run."
    )
    parser.add_argument(
        "--train-run-dir",
        type=Path,
        required=True,
        help="Path to an existing context_classifier training run directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = backfill_training_run_scientific_artifacts(args.train_run_dir.resolve())
    print(f"Train run dir: {result['train_run_dir']}")
    print(f"Environment manifest: {result['environment_manifest_path']}")
    print(f"Scientific run manifest: {result['scientific_run_manifest_path']}")


if __name__ == "__main__":
    main()
