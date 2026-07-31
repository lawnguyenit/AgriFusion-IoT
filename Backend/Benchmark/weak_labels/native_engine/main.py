from __future__ import annotations

import argparse
import sys

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.weak_labels.native_engine import NativeEngineConfig, build_native_label_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the contract-gated native semantic label engine.")
    parser.add_argument("--semantic-contract-run-dir", type=Path, required=True)
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument("--canonical-history", type=Path, required=True)
    parser.add_argument("--canonical-evidence-schema", type=Path, required=True)
    parser.add_argument("--sensor-dependency-registry", type=Path, required=True)
    parser.add_argument("--segment-manifest", type=Path, required=True)
    parser.add_argument("--expected-difference-contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--operationalization-id", default=None)
    parser.add_argument("--engine-mode", choices=("NATIVE", "SHADOW"), default="NATIVE")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_native_label_artifacts(
        NativeEngineConfig(
            semantic_contract_run_dir=args.semantic_contract_run_dir,
            protocol_registry_run_dir=args.protocol_registry_run_dir,
            canonical_history_path=args.canonical_history,
            canonical_evidence_schema_path=args.canonical_evidence_schema,
            sensor_dependency_registry_path=args.sensor_dependency_registry,
            segment_manifest_path=args.segment_manifest,
            expected_difference_contract_path=args.expected_difference_contract,
            output_root=args.output_root,
            operationalization_id=args.operationalization_id,
            engine_mode=args.engine_mode,
        )
    )
    print(f"native engine status: {result.status}")
    print(f"run id: {result.run_id}")
    print(f"output dir: {result.output_dir}")


if __name__ == "__main__":
    main()
