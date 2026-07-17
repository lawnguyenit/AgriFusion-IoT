from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import EVALUATION_PROTOCOLS_ROOT
from Backend.Benchmark.evaluation_protocols.pipeline.smoke import run_smoke_training


def _default_latest_protocol_run() -> Path:
    artifacts_root = EVALUATION_PROTOCOLS_ROOT / "artifacts"
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()] if artifacts_root.exists() else []
    if not candidates:
        raise FileNotFoundError("No evaluation_protocols artifact runs were found under Backend/Benchmark/evaluation_protocols/artifacts.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run staged smoke training from an evaluation_protocols primary runner manifest."
    )
    parser.add_argument("--protocol-run-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol_run_dir = args.protocol_run_dir.resolve() if args.protocol_run_dir is not None else _default_latest_protocol_run().resolve()
    result = run_smoke_training(protocol_run_dir)
    print("evaluation_protocols smoke training complete")
    print(f"Protocol run: {protocol_run_dir}")
    print(f"Smoke output dir: {result.output_dir}")
    print(f"Ready for smoke train: {result.readiness_report['ready_for_smoke_train']}")


if __name__ == "__main__":
    main()
