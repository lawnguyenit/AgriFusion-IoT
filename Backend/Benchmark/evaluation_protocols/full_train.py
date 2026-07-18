from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import EVALUATION_PROTOCOLS_ROOT
from Backend.Benchmark.evaluation_protocols.pipeline.full import run_full_training


def _default_latest_protocol_run() -> Path:
    artifacts_root = EVALUATION_PROTOCOLS_ROOT / "artifacts"
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()] if artifacts_root.exists() else []
    if not candidates:
        raise FileNotFoundError("No evaluation_protocols artifact runs were found under Backend/Benchmark/evaluation_protocols/artifacts.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full primary benchmark from an evaluation_protocols runner manifest."
    )
    parser.add_argument("--protocol-run-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol_run_dir = args.protocol_run_dir.resolve() if args.protocol_run_dir is not None else _default_latest_protocol_run().resolve()
    result = run_full_training(protocol_run_dir)
    print("evaluation_protocols full training complete")
    print(f"Protocol run: {protocol_run_dir}")
    print(f"Full output dir: {result.output_dir}")
    print(f"Ready for full benchmark: {result.readiness_report['ready_for_full_benchmark']}")


if __name__ == "__main__":
    main()
