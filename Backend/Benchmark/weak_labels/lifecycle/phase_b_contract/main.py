from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract import PhaseBConfig, build_phase_b_decision_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase B E1 semantic decision pack.")
    parser.add_argument("--phase-a-run-dir", type=Path, required=True)
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument("--canonical-history", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_phase_b_decision_pack(
        PhaseBConfig(
            phase_a_run_dir=args.phase_a_run_dir,
            protocol_registry_run_dir=args.protocol_registry_run_dir,
            canonical_history_path=args.canonical_history,
            output_root=args.output_root,
        )
    )
    print(f"Phase B1 decision pack: {result.output_dir}")
    print(f"Status: {result.status}")


if __name__ == "__main__":
    main()
