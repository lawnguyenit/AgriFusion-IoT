from __future__ import annotations

import argparse
from pathlib import Path


from agrifusion_research.core.model_suite.protocol_training.full import run_full_training


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full primary benchmark from an evaluation_protocols runner manifest."
    )
    parser.add_argument("--protocol-run-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-unaudited",
        action="store_true",
        help="Train even if the protocol run is not validation_status=ready; recorded in the readiness report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol_run_dir = args.protocol_run_dir.resolve()
    result = run_full_training(protocol_run_dir, allow_unaudited=args.allow_unaudited)
    print("evaluation_protocols full training complete")
    print(f"Protocol run: {protocol_run_dir}")
    print(f"Full output dir: {result.output_dir}")
    print(f"Ready for full benchmark: {result.readiness_report['ready_for_full_benchmark']}")


if __name__ == "__main__":
    main()
