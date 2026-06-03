from __future__ import annotations

import argparse
from pathlib import Path
from collections import OrderedDict

from .engine.simulator_pipeline import SimulatorPipeline
from .engine.real_train_target import (
    build_explicit_real_train_sizing_target,
    estimate_real_train_sizing_target,
)
from .scenarios.base import ScenarioSpec

SCENARIO_NAME_ALIASES = {
    "rain_humid_context": "rain_or_fertigation_context",
    "fertigation_spike": "rain_or_fertigation_context",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sinh CSV mo phong theo schema flb_input_aligned.csv de phuc vu benchmark/train."
    )
    parser.add_argument(
        "--seed-limit",
        type=int,
        default=0,
        help="So dong Layer1 align gan nhat dung lam seed baseline. 0 = dung toan bo seed.",
    )
    parser.add_argument(
        "--normal-count",
        type=int,
        default=600,
        help="So dong normal_context muon chen vao timeline synthetic.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario theo format name:count:intensity . Vi du water_deficit:300:0.85",
    )
    parser.add_argument(
        "--count-multiplier",
        type=float,
        default=1.0,
        help="He so nhan vao normal_count va scenario.count. Vi du 3.0 se bien 300 thanh 900.",
    )
    parser.add_argument(
        "--use-real-train-target",
        action="store_true",
        help="Bat che do auto-scale theo kich thuoc train real. Mac dinh tat de giu count tuyet doi nhu truoc.",
    )
    parser.add_argument(
        "--target-real-train-multiplier",
        type=float,
        default=3.0,
        help="He so nhan so dong train real de tinh tong so dong synthetic can sinh. Mac dinh = 3.0.",
    )
    parser.add_argument(
        "--real-train-row-count",
        type=int,
        default=0,
        help="Neu > 0, bo qua buoc estimate split va dung truc tiep gia tri nay lam so dong train real.",
    )
    parser.add_argument(
        "--real-event-csv",
        type=Path,
        default=None,
        help="CSV real labeled de estimate kich thuoc train real. Mac dinh dung artifact cua context_classifier.",
    )
    parser.add_argument(
        "--label-scheme",
        type=str,
        default="option2_4class",
        help="Label scheme dung khi estimate split real cho auto-target.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
        help="Train ratio dung khi estimate split real cho auto-target.",
    )
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.15,
        help="Validation ratio dung khi estimate split real cho auto-target.",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.15,
        help="Test ratio dung khi estimate split real cho auto-target.",
    )
    parser.add_argument(
        "--purge-gap-minutes",
        type=int,
        default=1440,
        help="Purge gap minutes dung khi estimate split real cho auto-target.",
    )
    parser.add_argument(
        "--split-strategy",
        type=str,
        default="coverage_aware_temporal",
        help="Split strategy dung khi estimate split real cho auto-target.",
    )
    return parser.parse_args()


def parse_scenario_specs(raw_specs: list[str]) -> list[ScenarioSpec]:
    if not raw_specs:
        return [
            ScenarioSpec(name="packet_loss", count=300, intensity=0.8),
            ScenarioSpec(name="rain_or_fertigation_context", count=600, intensity=0.85),
            ScenarioSpec(name="water_deficit", count=300, intensity=0.85),
        ]

    merged_specs: "OrderedDict[str, dict[str, float]]" = OrderedDict()
    for raw in raw_specs:
        parts = raw.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError(f"Scenario khong hop le: {raw}")
        name = SCENARIO_NAME_ALIASES.get(parts[0].strip(), parts[0].strip())
        count = int(parts[1])
        intensity = 1.0 if len(parts) == 2 else float(parts[2])
        count = max(1, count)
        intensity = max(0.0, intensity)
        if name not in merged_specs:
            merged_specs[name] = {
                "count": 0,
                "weighted_intensity_sum": 0.0,
            }
        merged_specs[name]["count"] += count
        merged_specs[name]["weighted_intensity_sum"] += intensity * count

    specs: list[ScenarioSpec] = []
    for name, payload in merged_specs.items():
        merged_count = int(payload["count"])
        weighted_intensity_sum = float(payload["weighted_intensity_sum"])
        merged_intensity = 0.0 if merged_count <= 0 else weighted_intensity_sum / merged_count
        specs.append(
            ScenarioSpec(
                name=name,
                count=merged_count,
                intensity=merged_intensity,
            )
        )
    return specs


def scale_scenario_specs(specs: list[ScenarioSpec], multiplier: float) -> list[ScenarioSpec]:
    if multiplier <= 0:
        raise ValueError(f"count multiplier must be positive, got {multiplier}")
    if abs(multiplier - 1.0) < 1e-9:
        return list(specs)
    scaled_specs: list[ScenarioSpec] = []
    for spec in specs:
        scaled_specs.append(
            ScenarioSpec(
                name=spec.name,
                count=max(1, int(round(spec.count * multiplier))),
                intensity=spec.intensity,
            )
        )
    return scaled_specs


def main() -> None:
    args = parse_args()
    scenario_specs = scale_scenario_specs(parse_scenario_specs(args.scenario), args.count_multiplier)
    normal_count = max(0, int(round(args.normal_count * args.count_multiplier)))
    sizing_target = None
    if args.use_real_train_target:
        sizing_kwargs = {
            "multiplier": args.target_real_train_multiplier,
            "real_event_csv": args.real_event_csv,
            "label_scheme": args.label_scheme,
            "train_ratio": args.train_ratio,
            "validation_ratio": args.validation_ratio,
            "test_ratio": args.test_ratio,
            "purge_gap_minutes": args.purge_gap_minutes,
            "split_strategy": args.split_strategy,
        }
        if args.real_train_row_count > 0:
            sizing_target = build_explicit_real_train_sizing_target(
                real_train_row_count=args.real_train_row_count,
                **sizing_kwargs,
            )
        else:
            sizing_target = estimate_real_train_sizing_target(**sizing_kwargs)

    result = SimulatorPipeline().run(
        scenario_specs=scenario_specs,
        seed_limit=args.seed_limit,
        normal_count=normal_count,
        real_train_sizing_target=sizing_target,
    )
    print("--- Simulator hoan tat ---")
    print(f"Run dir: {result.run_dir}")
    print(f"Generated records: {result.generated_record_count}")
    print(f"Applied count multiplier: {args.count_multiplier}")
    if sizing_target is not None:
        print(
            "Real-train target:"
            f" train_rows={sizing_target.real_train_row_count},"
            f" multiplier={sizing_target.multiplier},"
            f" synthetic_target={sizing_target.target_total_records},"
            f" source={sizing_target.source}"
        )
    print(f"Interval seconds: {result.interval_seconds}")
    print(f"Simulation start ts: {result.simulation_start_ts}")
    print(f"Simulation end ts: {result.simulation_end_ts}")
    print(f"Benchmark CSV: {result.csv_path}")
    print(f"Labeled CSV: {result.labeled_csv_path}")
    print(f"Gap-aware CSV: {result.gap_aware_csv_path}")
    print(f"Label summary: {result.label_summary_path}")
    print(f"Augmentation taxonomy: {result.augmentation_taxonomy_path}")
    print(f"Manifest: {result.manifest_path}")


if __name__ == "__main__":
    main()
