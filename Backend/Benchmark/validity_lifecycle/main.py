from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import VALIDITY_LIFECYCLE_ROOT
from Backend.Benchmark.validity_lifecycle import ValidityLifecycleConfig, build_validity_lifecycle
from Backend.Benchmark.validity_lifecycle.defaults import default_environment_specs
from Backend.Benchmark.validity_lifecycle.loaders import resolve_latest_evaluation_protocol_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build validity lifecycle audits from an authoritative evaluation_protocols run."
    )
    parser.add_argument("--evaluation-protocol-run-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=VALIDITY_LIFECYCLE_ROOT / "artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol_run_dir = (
        args.evaluation_protocol_run_dir.resolve()
        if args.evaluation_protocol_run_dir is not None
        else resolve_latest_evaluation_protocol_run().resolve()
    )
    result = build_validity_lifecycle(
        ValidityLifecycleConfig(
            evaluation_protocol_run_dir=protocol_run_dir,
            output_root=args.output_root.resolve(),
            environment_specs=default_environment_specs(),
        )
    )
    print("validity_lifecycle build complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"Overall status: {result.overall_status}")
    print(f"Observation count: {result.observation_count}")


if __name__ == "__main__":
    main()
