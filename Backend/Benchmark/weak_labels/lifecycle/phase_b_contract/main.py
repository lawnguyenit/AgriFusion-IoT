from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract import (
    PhaseB2Config,
    PhaseBConfig,
    build_phase_b_decision_pack,
    freeze_phase_b_contract,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase B1 decision-pack or B2 freeze.")
    subparsers = parser.add_subparsers(dest="command")
    freeze = subparsers.add_parser("freeze", help="Validate review inputs and freeze Phase B2 contract.")
    for name, required in (
        ("phase-a-run-dir", True),
        ("phase-b1-run-dir", True),
        ("protocol-registry-run-dir", True),
        ("review-decision", True),
        ("anchor-safety-audit", True),
        ("distribution-audit", True),
        ("derived-evidence-contract", True),
        ("continuity-contract", True),
        ("window-contract", True),
        ("expected-difference-contract", True),
        ("canonical-history", True),
        ("output-root", True),
    ):
        freeze.add_argument(f"--{name}", type=Path, required=required)
    return parser


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "freeze":
        args = _build_parser().parse_args(argv)
        result = freeze_phase_b_contract(
            PhaseB2Config(
                phase_a_run_dir=args.phase_a_run_dir,
                phase_b1_decision_pack_dir=args.phase_b1_run_dir,
                protocol_registry_run_dir=args.protocol_registry_run_dir,
                review_decision_path=args.review_decision,
                anchor_safety_audit_path=args.anchor_safety_audit,
                distribution_audit_path=args.distribution_audit,
                derived_evidence_contract_path=args.derived_evidence_contract,
                continuity_contract_path=args.continuity_contract,
                window_contract_path=args.window_contract,
                expected_difference_contract_path=args.expected_difference_contract,
                canonical_history_path=args.canonical_history,
                output_root=args.output_root,
            )
        )
        print(f"Phase B2 status: {result.status}")
        if result.output_dir:
            print(f"Semantic contract: {result.output_dir}")
            print(f"Frozen registry: {result.frozen_registry_dir}")
        if result.reason:
            print(f"Reason: {result.reason}")
        return

    parser = argparse.ArgumentParser(description="Build the Phase B1 E1 semantic decision pack.")
    parser.add_argument("--phase-a-run-dir", type=Path, required=True)
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument("--canonical-history", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
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
