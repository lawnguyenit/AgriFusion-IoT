from __future__ import annotations

import argparse

from .engine.simulator_pipeline import SimulatorPipeline
from .scenarios.base import ScenarioSpec


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
        help="Tong so dong normal_context muon chen vao timeline synthetic.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario theo format name:count:intensity . Vi du water_deficit:300:0.85",
    )
    return parser.parse_args()


def parse_scenario_specs(raw_specs: list[str]) -> list[ScenarioSpec]:
    if not raw_specs:
        return [
            ScenarioSpec(name="packet_loss", count=300, intensity=0.8),
            ScenarioSpec(name="rain_humid_context", count=300, intensity=0.8),
            ScenarioSpec(name="fertigation_spike", count=300, intensity=0.9),
            ScenarioSpec(name="water_deficit", count=300, intensity=0.85),
        ]

    specs: list[ScenarioSpec] = []
    for raw in raw_specs:
        parts = raw.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError(f"Scenario khong hop le: {raw}")
        name = parts[0].strip()
        count = int(parts[1])
        intensity = 1.0 if len(parts) == 2 else float(parts[2])
        specs.append(
            ScenarioSpec(
                name=name,
                count=max(1, count),
                intensity=max(0.0, intensity),
            )
        )
    return specs


def main() -> None:
    args = parse_args()
    scenario_specs = parse_scenario_specs(args.scenario)
    result = SimulatorPipeline().run(
        scenario_specs=scenario_specs,
        seed_limit=args.seed_limit,
        normal_count=args.normal_count,
    )
    print("--- Simulator hoan tat ---")
    print(f"Run dir: {result.run_dir}")
    print(f"Generated records: {result.generated_record_count}")
    print(f"Interval seconds: {result.interval_seconds}")
    print(f"Simulation start ts: {result.simulation_start_ts}")
    print(f"Simulation end ts: {result.simulation_end_ts}")
    print(f"Benchmark CSV: {result.csv_path}")
    print(f"Labeled CSV: {result.labeled_csv_path}")
    print(f"Gap-aware CSV: {result.gap_aware_csv_path}")
    print(f"Label summary: {result.label_summary_path}")
    print(f"Manifest: {result.manifest_path}")


if __name__ == "__main__":
    main()
