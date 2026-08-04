from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import VALIDITY_LIFECYCLE_ROOT
from Backend.Benchmark.validity_lifecycle import ValidityLifecycleConfig, build_validity_lifecycle
from Backend.Benchmark.validity_lifecycle.defaults import environment_specs_from_protocol_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build validity lifecycle audits from an authoritative evaluation_protocols run."
    )
    parser.add_argument("--evaluation-protocol-run-dir", type=Path, required=True)
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=VALIDITY_LIFECYCLE_ROOT / "artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol_run_dir = args.evaluation_protocol_run_dir.resolve()
    result = build_validity_lifecycle(
        ValidityLifecycleConfig(
            protocol_registry_run_dir=args.protocol_registry_run_dir.resolve(),
            evaluation_protocol_run_dir=protocol_run_dir,
            output_root=args.output_root.resolve(),
            environment_specs=environment_specs_from_protocol_registry(
                args.protocol_registry_run_dir.resolve()
            ),
        )
    )
    print("validity_lifecycle build complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"Overall status: {result.overall_status}")
    print(f"Observation count: {result.observation_count}")


if __name__ == "__main__":
    main()
