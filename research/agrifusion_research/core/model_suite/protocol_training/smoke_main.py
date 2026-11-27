from __future__ import annotations

import argparse
from pathlib import Path


from agrifusion_research.core.model_suite.protocol_training.smoke import run_smoke_training


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run staged smoke training from an evaluation_protocols primary runner manifest."
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
    result = run_smoke_training(protocol_run_dir, allow_unaudited=args.allow_unaudited)
    print("evaluation_protocols smoke training complete")
    print(f"Protocol run: {protocol_run_dir}")
    print(f"Smoke output dir: {result.output_dir}")
    print(f"Ready for smoke train: {result.readiness_report['ready_for_smoke_train']}")


if __name__ == "__main__":
    main()
