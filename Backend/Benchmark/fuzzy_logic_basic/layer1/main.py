from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Config.IO.io_csv import write_csv_rows  # noqa: E402
from Backend.Config.IO.io_json import write_json  # noqa: E402
from Backend.Config.path_manager import ensure_path_exists  # noqa: E402

from Backend.Benchmark.fuzzy_logic_basic.layer1.alignment import AlignmentResult, align_layer1_records  # noqa: E402
from Backend.Benchmark.fuzzy_logic_basic.layer1.config import AlignmentConfig, default_input_root, default_output_root  # noqa: E402


CSV_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "pH",
    "N",
    "P",
    "K",
    "ec_npk_consistency_score",
    "ec_npk_consistency_flag",
]
DATA_COLUMNS = list(CSV_COLUMNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Layer1 FLB input alignment CSV from existing Layer1 histories."
    )
    parser.add_argument("--input-root", type=Path, default=default_input_root(), help="Layer1 root directory.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root(),
        help="Benchmark dataset output directory.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for a dry run.")
    parser.add_argument(
        "--anchor-cluster-gap-sec",
        type=int,
        default=300,
        help="Cluster timestamps within this gap into one master timestamp.",
    )
    parser.add_argument(
        "--family-match-tolerance-sec",
        type=int,
        default=1200,
        help="Maximum allowed time offset when joining a family record to a master timestamp.",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> AlignmentConfig:
    return AlignmentConfig(
        input_root=args.input_root,
        output_root=args.output_root,
        anchor_cluster_gap_sec=args.anchor_cluster_gap_sec,
        family_match_tolerance_sec=args.family_match_tolerance_sec,
    )


def _count_missing(rows: list[dict[str, object]], fieldnames: list[str]) -> dict[str, int]:
    counts = {field: 0 for field in fieldnames}
    for row in rows:
        for field in counts:
            value = row.get(field)
            if value is None or value == "":
                counts[field] += 1
    return counts


def run_alignment(config: AlignmentConfig, limit: int | None = None) -> AlignmentResult:
    rows, input_counts, _, ec_model, _ = align_layer1_records(config)
    if limit is not None:
        rows = rows[: max(0, limit)]

    # Kiểm tra và tạo thư mục đầu ra nếu chưa tồn tại
    ensure_path_exists(config.output_root)
    csv_path = config.output_root / "flb_input_aligned.csv"
    manifest_path = config.output_root / "manifest.json"

    # Viết kết quả ra CSV
    write_csv_rows(rows, csv_path, CSV_COLUMNS)

    missing_counts = _count_missing(rows, DATA_COLUMNS)
    flag_distribution: dict[str, int] = {}
    for row in rows:
        raw_flag = row.get("ec_npk_consistency_flag")
        flag = "unknown" if raw_flag is None else str(int(raw_flag))
        flag_distribution[flag] = flag_distribution.get(flag, 0) + 1

    manifest = {
        "schema_version": 1,
        "pipeline": "flb_layer1_alignment",
        "input_root": str(config.input_root),
        "output_root": str(config.output_root),
        "row_count": len(rows),
        "input_counts": input_counts,
        "missing_counts": missing_counts,
        "flag_distribution": flag_distribution,
        "ec_model": {
            "slope": ec_model.slope,
            "intercept": ec_model.intercept,
            "sample_count": ec_model.sample_count,
            "r2": ec_model.r2,
        },
        "notes": {
            "layer1_input_only": True,
            "meteo_not_exported": True,
            "cluster_gap_sec": config.anchor_cluster_gap_sec,
            "family_match_tolerance_sec": config.family_match_tolerance_sec,
            "csv_columns": CSV_COLUMNS,
        },
    }
    write_json(manifest_path, manifest)

    return AlignmentResult(
        input_root=config.input_root,
        output_root=config.output_root,
        row_count=len(rows),
        input_counts=input_counts,
        missing_counts=missing_counts,
        flag_distribution=flag_distribution,
        csv_path=csv_path,
        manifest_path=manifest_path,
        ec_model=ec_model,
        rows=rows,
    )


def main() -> None:
    args = parse_args()
    config = build_config(args)
    result = run_alignment(config=config, limit=args.limit)

    print("Layer1 FLB alignment complete")
    print(f"Input root: {result.input_root}")
    print(f"Output root: {result.output_root}")
    print(f"CSV: {result.csv_path}")
    print(f"Manifest: {result.manifest_path}")
    print(
        "Input records: "
        f"npk={result.input_counts.get('npk_records', 0)}, "
        f"sht30={result.input_counts.get('sht30_records', 0)}, "
        f"meteo={result.input_counts.get('meteo_records', 0)}, "
        f"anchors={result.input_counts.get('anchor_count', 0)}"
    )
    print(f"Aligned rows: {result.row_count}")
    print(f"Missing counts: {result.missing_counts}")
    print(f"ec_npk_consistency_flag distribution: {result.flag_distribution}")
    print(
        "EC model: "
        f"slope={result.ec_model.slope:.6f}, "
        f"intercept={result.ec_model.intercept:.6f}, "
        f"samples={result.ec_model.sample_count}, "
        f"r2={None if result.ec_model.r2 is None else round(result.ec_model.r2, 4)}"
    )


if __name__ == "__main__":
    main()
