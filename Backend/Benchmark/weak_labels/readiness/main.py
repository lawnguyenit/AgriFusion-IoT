from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import WEAK_LABELS_ROOT
from Backend.Benchmark.weak_labels.readiness import PhaseAReadinessConfig, build_phase_a_readiness
from Backend.Config.paths import BACKEND_PATHS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run audit-only weak-label Phase A readiness analysis.")
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument(
        "--canonical-history",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "canonical" / "telemetry_history.csv",
    )
    parser.add_argument(
        "--layer1-manifest",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "manifest.json",
    )
    parser.add_argument("--baseline-weak-label-run-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, default=WEAK_LABELS_ROOT / "readiness" / "artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_phase_a_readiness(
        PhaseAReadinessConfig(
            protocol_registry_run_dir=args.protocol_registry_run_dir.resolve(),
            canonical_history_path=args.canonical_history.resolve(),
            canonical_manifest_path=args.layer1_manifest.resolve(),
            baseline_weak_label_run_dirs=tuple(path.resolve() for path in args.baseline_weak_label_run_dir),
            output_root=args.output_root.resolve(),
        )
    )
    print("Phase A readiness audit complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"Overall status: {result.overall_status}")
    print(f"E1 records: {result.e1_record_count}")


if __name__ == "__main__":
    main()
