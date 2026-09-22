from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.source_intake.adapter import (  # noqa: E402
    build_canonical_candidate,
    build_legacy_projection,
    build_segment_manifest,
    load_flattened_source,
)
from Backend.Benchmark.source_intake.audit import build_audit  # noqa: E402
from Backend.Benchmark.source_intake.reporting import write_intake_artifact  # noqa: E402
from Backend.Config.paths import BACKEND_PATHS  # noqa: E402
import pandas as pd  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a flattened Firebase CSV and emit an additive Layer1-compatible candidate."
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=Path(r"C:\Users\lawng\Downloads\AgriFusion_Node1_only_clean.csv"),
        help="Flattened Firebase CSV export.",
    )
    parser.add_argument(
        "--old-canonical",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "canonical" / "telemetry_history.csv",
        help="Existing canonical history used for overlap and compatibility comparison.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BACKEND_PATHS.benchmark_dir / "source_intake" / "artifacts",
        help="Additive artifact root. Existing canonical outputs are never written here.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = load_flattened_source(args.source_csv)
    old_canonical = pd.read_csv(args.old_canonical.resolve(), low_memory=False)
    candidate = build_canonical_candidate(source)
    old_columns = list(old_canonical.columns)
    legacy_projection = build_legacy_projection(candidate, old_columns)
    auxiliary = source.copy()
    auxiliary.insert(0, "record.id", _record_ids(source))
    summary, details = build_audit(source, old_canonical, candidate)
    segment_manifest = build_segment_manifest(candidate)
    run_id, output_dir, report_path = write_intake_artifact(
        output_root=args.output_root,
        source_path=args.source_csv,
        old_canonical_path=args.old_canonical,
        source=source,
        candidate=candidate,
        legacy_projection=legacy_projection,
        auxiliary=auxiliary,
        segment_manifest=segment_manifest,
        summary=summary,
        details=details,
    )
    print("New Firebase CSV intake audit complete")
    print(f"Run id: {run_id}")
    print(f"Output dir: {output_dir}")
    print(f"Report: {report_path}")
    print(f"Rows: {summary['source_rows']}")
    print(f"Shared keys: {summary['shared_key_count']}")
    print(f"New-only keys: {summary['new_only_key_count']}")


def _record_ids(source: pd.DataFrame) -> pd.Series:
    return (
        source["node_id"].astype("string")
        + ":"
        + source["raw_date_key"].astype("string")
        + ":"
        + pd.to_numeric(source["event_key"], errors="coerce").astype("Int64").astype("string")
    )


if __name__ == "__main__":
    main()
