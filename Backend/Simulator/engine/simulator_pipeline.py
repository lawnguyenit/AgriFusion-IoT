from __future__ import annotations

import csv
import json
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config.paths import SimulatorPaths
from .augmentation_taxonomy import build_augmentation_taxonomy
from .real_train_target import RealTrainSizingTarget
from ..scenarios.base import Scenario, ScenarioContext, ScenarioSpec
from ..scenarios.packet_loss import PacketLossScenario
from ..scenarios.rain_or_fertigation_context import RainOrFertigationContextScenario
from ..scenarios.water_deficit import WaterDeficitScenario
from ..seed.aligned_seed_reader import load_aligned_seed_rows

BENCHMARK_COLUMNS = [
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
]

LABELED_EXTRA_COLUMNS = [
    "scenario_label",
    "timeline_state",
    "episode_id",
    "phase_name",
    "is_synthetic",
    "scenario_intensity",
    "scenario_progress",
    "effect_strength",
    "source_seed_timestamp",
]

GAP_AWARE_EXTRA_COLUMNS = [
    "record_present",
    "system_context",
    "recovery_hint",
]

EVENT_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "packet_loss": (6, 28),
    "rain_or_fertigation_context": (8, 24),
    "water_deficit": (40, 96),
}

SCENARIO_REGISTRY: dict[str, Scenario] = {
    PacketLossScenario.name: PacketLossScenario(),
    RainOrFertigationContextScenario.name: RainOrFertigationContextScenario(),
    WaterDeficitScenario.name: WaterDeficitScenario(),
}


@dataclass(frozen=True)
class EpisodePlan:
    scenario_name: str
    duration_steps: int
    intensity: float


@dataclass(frozen=True)
class EpisodeRun:
    episode_id: str
    scenario_name: str
    start_ts: int
    end_ts: int
    duration_steps: int
    intensity: float


@dataclass(frozen=True)
class SimulationRunResult:
    run_dir: Path
    csv_path: Path
    labeled_csv_path: Path
    gap_aware_csv_path: Path
    manifest_path: Path
    label_summary_path: Path
    augmentation_taxonomy_path: Path
    generated_record_count: int
    interval_seconds: int
    simulation_start_ts: int
    simulation_end_ts: int


class SimulatorPipeline:
    def __init__(self, paths: SimulatorPaths | None = None):
        self.paths = SimulatorPaths.discover() if paths is None else paths

    def run(
        self,
        *,
        scenario_specs: list[ScenarioSpec],
        seed_limit: int = 0,
        normal_count: int = 600,
        real_train_sizing_target: RealTrainSizingTarget | None = None,
    ) -> SimulationRunResult:
        aligned_dataset = load_aligned_seed_rows(self.paths.layer1_root)
        seed_rows = aligned_dataset.rows if seed_limit <= 0 else aligned_dataset.rows[-seed_limit:]
        if not seed_rows:
            raise ValueError("Khong co seed Layer1 de sinh du lieu mo phong.")

        interval_seconds = _estimate_interval_seconds(seed_rows)
        latest_seed_ts = int(seed_rows[-1]["timestamp"])
        slot_map = _build_slot_map(seed_rows, interval_seconds)
        rng = random.Random(20260526)
        resolved_normal_count, resolved_scenario_specs, allocation_summary = _resolve_generation_mix(
            normal_count=normal_count,
            scenario_specs=scenario_specs,
            real_train_sizing_target=real_train_sizing_target,
        )

        episode_plans = _build_episode_plans(resolved_scenario_specs, latest_seed_ts, interval_seconds, rng)
        normal_segments = _allocate_normal_segments(resolved_normal_count, len(episode_plans) + 1, rng)

        benchmark_rows: list[dict[str, Any]] = []
        labeled_rows: list[dict[str, Any]] = []
        gap_aware_rows: list[dict[str, Any]] = []
        episode_runs: list[EpisodeRun] = []

        current_ts = latest_seed_ts + interval_seconds
        simulation_start_ts = current_ts
        episode_counter = 0

        # Prelude normal segment
        current_ts = self._emit_normal_rows(
            count=normal_segments[0],
            current_ts=current_ts,
            interval_seconds=interval_seconds,
            slot_map=slot_map,
            seed_rows=seed_rows,
            benchmark_rows=benchmark_rows,
            labeled_rows=labeled_rows,
            gap_aware_rows=gap_aware_rows,
        )

        for index, plan in enumerate(episode_plans):
            scenario = SCENARIO_REGISTRY[plan.scenario_name]
            current_ts = _advance_to_valid_hour(current_ts, scenario, interval_seconds)
            episode_counter += 1
            episode_id = f"{plan.scenario_name}_{episode_counter:03d}"
            episode_start_ts = current_ts

            for step_index in range(plan.duration_steps):
                base_row = _select_seed_row(slot_map, seed_rows, current_ts, interval_seconds)
                base_benchmark_row = _clone_benchmark_row(base_row)
                base_benchmark_row["timestamp"] = current_ts
                raw_progress = step_index / max(1, plan.duration_steps - 1)
                phase_name, effect_strength = _phase_profile(raw_progress)

                if plan.scenario_name == "packet_loss":
                    gap_row = _build_gap_row(
                        timestamp=current_ts,
                        episode_id=episode_id,
                        intensity=plan.intensity,
                        progress=raw_progress,
                        effect_strength=effect_strength,
                        phase_name=phase_name,
                        source_seed_timestamp=int(base_row["timestamp"]),
                    )
                    gap_aware_rows.append(gap_row)
                else:
                    context = ScenarioContext(
                        row_index=step_index,
                        row_count=plan.duration_steps,
                        scenario_progress=raw_progress,
                        effect_strength=effect_strength,
                        phase_name=phase_name,
                        intensity=plan.intensity,
                        interval_seconds=interval_seconds,
                        timestamp=current_ts,
                    )
                    benchmark_row = scenario.mutate(base_benchmark_row, context)
                    benchmark_row = _sanitize_row(benchmark_row)
                    labeled_row = _build_labeled_row(
                        benchmark_row,
                        scenario_label=plan.scenario_name,
                        timeline_state="event",
                        episode_id=episode_id,
                        phase_name=phase_name,
                        intensity=plan.intensity,
                        progress=raw_progress,
                        effect_strength=effect_strength,
                        source_seed_timestamp=int(base_row["timestamp"]),
                        record_present=1,
                        system_context="environment_or_operation_event",
                        recovery_hint="",
                    )
                    benchmark_rows.append(benchmark_row)
                    labeled_rows.append(labeled_row)
                    gap_aware_rows.append(dict(labeled_row))
                current_ts += interval_seconds

            episode_runs.append(
                EpisodeRun(
                    episode_id=episode_id,
                    scenario_name=plan.scenario_name,
                    start_ts=episode_start_ts,
                    end_ts=current_ts - interval_seconds,
                    duration_steps=plan.duration_steps,
                    intensity=plan.intensity,
                )
            )

            current_ts = self._emit_normal_rows(
                count=normal_segments[index + 1],
                current_ts=current_ts,
                interval_seconds=interval_seconds,
                slot_map=slot_map,
                seed_rows=seed_rows,
                benchmark_rows=benchmark_rows,
                labeled_rows=labeled_rows,
                gap_aware_rows=gap_aware_rows,
            )

        simulation_end_ts = current_ts - interval_seconds

        run_id = datetime.now().strftime("sim_%d%m%Y_%H%M%S")
        run_dir = self.paths.outputs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        csv_path = run_dir / "synthetic_flb_input.csv"
        labeled_csv_path = run_dir / "synthetic_flb_input_labeled.csv"
        gap_aware_csv_path = run_dir / "synthetic_flb_gap_aware.csv"
        manifest_path = run_dir / "generation_manifest.json"
        label_summary_path = run_dir / "label_summary.json"
        augmentation_taxonomy_path = run_dir / "augmentation_taxonomy.json"

        _write_csv(csv_path, BENCHMARK_COLUMNS, benchmark_rows)
        _write_csv(labeled_csv_path, BENCHMARK_COLUMNS + LABELED_EXTRA_COLUMNS + GAP_AWARE_EXTRA_COLUMNS, labeled_rows)
        _write_csv(gap_aware_csv_path, BENCHMARK_COLUMNS + LABELED_EXTRA_COLUMNS + GAP_AWARE_EXTRA_COLUMNS, gap_aware_rows)

        label_summary = _build_label_summary(gap_aware_rows)
        augmentation_taxonomy = build_augmentation_taxonomy(gap_aware_rows)
        _write_json(
            label_summary_path,
            {
                **label_summary,
                "requested_normal_count": normal_count,
                "resolved_normal_count": resolved_normal_count,
                "actual_normal_count": sum(1 for row in gap_aware_rows if row["scenario_label"] == "normal_context"),
            },
        )
        _write_json(augmentation_taxonomy_path, augmentation_taxonomy)
        _write_json(
            manifest_path,
            {
                "run_id": run_id,
                "input_root": str(self.paths.layer1_root),
                "seed_row_count": len(seed_rows),
                "requested_normal_count": normal_count,
                "resolved_normal_count": resolved_normal_count,
                "actual_normal_count": sum(1 for row in gap_aware_rows if row["scenario_label"] == "normal_context"),
                "benchmark_row_count": len(benchmark_rows),
                "gap_aware_row_count": len(gap_aware_rows),
                "packet_loss_missing_row_count": sum(
                    1
                    for row in gap_aware_rows
                    if row["scenario_label"] == "packet_loss" and int(row["record_present"]) == 0
                ),
                "interval_seconds": interval_seconds,
                "simulation_start_ts": simulation_start_ts,
                "simulation_end_ts": simulation_end_ts,
                "requested_scenario_specs": [
                    {"name": spec.name, "count": spec.count, "intensity": spec.intensity} for spec in scenario_specs
                ],
                "resolved_scenario_specs": [
                    {"name": spec.name, "count": spec.count, "intensity": spec.intensity}
                    for spec in resolved_scenario_specs
                ],
                "generation_mix": allocation_summary,
                "real_train_sizing_target": (
                    real_train_sizing_target.to_manifest_dict() if real_train_sizing_target is not None else {"enabled": False}
                ),
                "normal_segments": normal_segments,
                "episodes": [
                    {
                        "episode_id": episode.episode_id,
                        "scenario_name": episode.scenario_name,
                        "start_ts": episode.start_ts,
                        "end_ts": episode.end_ts,
                        "duration_steps": episode.duration_steps,
                        "duration_hours": round((episode.duration_steps * interval_seconds) / 3600, 3),
                        "intensity": episode.intensity,
                    }
                    for episode in episode_runs
                ],
                "seed_input_counts": aligned_dataset.input_counts,
                "seed_missing_counts": aligned_dataset.missing_counts,
                "output_files": {
                    "benchmark_csv": str(csv_path),
                    "labeled_csv": str(labeled_csv_path),
                    "gap_aware_csv": str(gap_aware_csv_path),
                    "label_summary": str(label_summary_path),
                    "augmentation_taxonomy": str(augmentation_taxonomy_path),
                },
                "augmentation_taxonomy": augmentation_taxonomy,
                "assumptions": [
                    "So dong normal duoc khong che bang normal_count thay vi de no phinh theo timeline.",
                    "Packet loss duoc bieu dien bang mat record trong gap-aware timeline.",
                    "Benchmark CSV giu schema flb_input_aligned.csv va tu nhien se co gap timestamp o outage.",
                    "Khi bat auto target, normal_count va scenario.count duoc dung nhu weight phan bo thay vi count tuyet doi.",
                ],
            },
        )

        return SimulationRunResult(
            run_dir=run_dir,
            csv_path=csv_path,
            labeled_csv_path=labeled_csv_path,
            gap_aware_csv_path=gap_aware_csv_path,
            manifest_path=manifest_path,
            label_summary_path=label_summary_path,
            augmentation_taxonomy_path=augmentation_taxonomy_path,
            generated_record_count=len(gap_aware_rows),
            interval_seconds=interval_seconds,
            simulation_start_ts=simulation_start_ts,
            simulation_end_ts=simulation_end_ts,
        )

    def _emit_normal_rows(
        self,
        *,
        count: int,
        current_ts: int,
        interval_seconds: int,
        slot_map: dict[int, list[dict[str, Any]]],
        seed_rows: list[dict[str, Any]],
        benchmark_rows: list[dict[str, Any]],
        labeled_rows: list[dict[str, Any]],
        gap_aware_rows: list[dict[str, Any]],
    ) -> int:
        ts_cursor = current_ts
        for _ in range(max(0, count)):
            base_row = _select_seed_row(slot_map, seed_rows, ts_cursor, interval_seconds)
            benchmark_row = _clone_benchmark_row(base_row)
            benchmark_row["timestamp"] = ts_cursor
            benchmark_row = _sanitize_row(benchmark_row)
            labeled_row = _build_labeled_row(
                benchmark_row,
                scenario_label="normal_context",
                timeline_state="normal",
                episode_id="",
                phase_name="baseline",
                intensity=0.0,
                progress=0.0,
                effect_strength=0.0,
                source_seed_timestamp=int(base_row["timestamp"]),
                record_present=1,
                system_context="nominal_operation",
                recovery_hint="",
            )
            benchmark_rows.append(benchmark_row)
            labeled_rows.append(labeled_row)
            gap_aware_rows.append(dict(labeled_row))
            ts_cursor += interval_seconds
        return ts_cursor


def _build_episode_plans(
    scenario_specs: list[ScenarioSpec],
    latest_seed_ts: int,
    interval_seconds: int,
    rng: random.Random,
) -> list[EpisodePlan]:
    scenario_order = [spec.name for spec in scenario_specs]
    spec_map = {spec.name: spec for spec in scenario_specs}
    remaining = {spec.name: spec.count for spec in scenario_specs}
    plans: list[EpisodePlan] = []
    current_ts = latest_seed_ts + interval_seconds
    cycle_index = 0

    while any(count > 0 for count in remaining.values()):
        scenario_name = _next_available_scenario(scenario_order, remaining, cycle_index)
        if scenario_name is None:
            break
        cycle_index = (scenario_order.index(scenario_name) + 1) % len(scenario_order)
        current_ts = _advance_to_valid_hour(current_ts, SCENARIO_REGISTRY[scenario_name], interval_seconds)
        duration_steps = _pick_episode_duration_steps(
            scenario_name=scenario_name,
            remaining_count=remaining[scenario_name],
            start_ts=current_ts,
            interval_seconds=interval_seconds,
            rng=rng,
        )
        plans.append(EpisodePlan(scenario_name=scenario_name, duration_steps=duration_steps, intensity=spec_map[scenario_name].intensity))
        remaining[scenario_name] -= duration_steps
        current_ts += duration_steps * interval_seconds
    return plans


def _allocate_normal_segments(normal_count: int, segment_count: int, rng: random.Random) -> list[int]:
    if segment_count <= 0:
        return []
    if normal_count <= 0:
        return [0 for _ in range(segment_count)]
    weights = [rng.uniform(0.75, 1.35) for _ in range(segment_count)]
    total_weight = sum(weights)
    raw = [normal_count * weight / total_weight for weight in weights]
    segments = [int(value) for value in raw]
    remainder = normal_count - sum(segments)
    for index in range(remainder):
        segments[index % segment_count] += 1
    return segments


def _resolve_generation_mix(
    *,
    normal_count: int,
    scenario_specs: list[ScenarioSpec],
    real_train_sizing_target: RealTrainSizingTarget | None,
) -> tuple[int, list[ScenarioSpec], dict[str, Any]]:
    if real_train_sizing_target is None:
        return (
            normal_count,
            list(scenario_specs),
            {
                "mode": "manual_counts",
                "target_total_records": normal_count + sum(spec.count for spec in scenario_specs),
                "normal_weight": normal_count,
                "scenario_weight_total": sum(spec.count for spec in scenario_specs),
            },
        )

    total_weight = max(0, normal_count) + sum(max(0, spec.count) for spec in scenario_specs)
    if total_weight <= 0:
        raise ValueError("Khong the auto-scale synthetic khi tong weight normal + scenario <= 0.")

    allocations = _largest_remainder_allocate(
        target_total=real_train_sizing_target.target_total_records,
        items=[("normal_context", max(0, normal_count))] + [(spec.name, max(0, spec.count)) for spec in scenario_specs],
    )
    resolved_normal_count = allocations.get("normal_context", 0)
    resolved_specs = [
        ScenarioSpec(name=spec.name, count=allocations.get(spec.name, 0), intensity=spec.intensity) for spec in scenario_specs
    ]
    return (
        resolved_normal_count,
        resolved_specs,
        {
            "mode": "real_train_multiplier",
            "target_total_records": real_train_sizing_target.target_total_records,
            "normal_weight": normal_count,
            "scenario_weight_total": sum(spec.count for spec in scenario_specs),
            "resolved_total_records": resolved_normal_count + sum(spec.count for spec in resolved_specs),
            "allocation_by_label": allocations,
        },
    )


def _largest_remainder_allocate(target_total: int, items: list[tuple[str, int]]) -> dict[str, int]:
    positive_items = [(name, weight) for name, weight in items if weight > 0]
    if target_total < 0:
        raise ValueError(f"target_total must be non-negative, got {target_total}")
    if not positive_items or target_total == 0:
        return {name: 0 for name, _ in items}

    total_weight = sum(weight for _, weight in positive_items)
    raw_allocations = [
        (name, weight, (target_total * weight) / total_weight)
        for name, weight in positive_items
    ]
    allocations = {name: int(raw_value) for name, _, raw_value in raw_allocations}
    remainder = target_total - sum(allocations.values())
    ranked = sorted(raw_allocations, key=lambda item: (item[2] - int(item[2]), item[1]), reverse=True)
    for index in range(remainder):
        name = ranked[index % len(ranked)][0]
        allocations[name] += 1
    for name, _ in items:
        allocations.setdefault(name, 0)
    return allocations


def _next_available_scenario(
    scenario_order: list[str],
    remaining: dict[str, int],
    cycle_index: int,
) -> str | None:
    for offset in range(len(scenario_order)):
        candidate = scenario_order[(cycle_index + offset) % len(scenario_order)]
        if remaining.get(candidate, 0) > 0:
            return candidate
    return None


def _pick_episode_duration_steps(
    *,
    scenario_name: str,
    remaining_count: int,
    start_ts: int,
    interval_seconds: int,
    rng: random.Random,
) -> int:
    min_steps, max_steps = EVENT_DURATION_RANGES[scenario_name]
    if scenario_name == "packet_loss":
        min_steps, max_steps = _packet_loss_duration_window(start_ts, interval_seconds, min_steps, max_steps, rng)
    if remaining_count <= max_steps:
        return remaining_count
    return rng.randint(min_steps, max_steps)


def _packet_loss_duration_window(
    start_ts: int,
    interval_seconds: int,
    default_min: int,
    default_max: int,
    rng: random.Random,
) -> tuple[int, int]:
    local_dt = _local_datetime(start_ts)
    hour = local_dt.hour
    if hour >= 18 or hour < 6:
        next_sunrise = local_dt.replace(hour=7, minute=0, second=0, microsecond=0)
        if hour >= 18:
            next_sunrise = next_sunrise + timedelta(days=1)
        steps_until_sunrise = max(1, int((next_sunrise - local_dt).total_seconds() // interval_seconds))
        min_steps = max(default_min, steps_until_sunrise)
        max_steps = min_steps + rng.randint(4, 14)
        return min_steps, max_steps
    if 6 <= hour < 11:
        min_steps = max(default_min, 6)
        max_steps = max(min_steps + 2, 20)
        return min_steps, max_steps
    min_steps = max(default_min, 8)
    max_steps = max(min_steps + 3, default_max)
    return min_steps, max_steps


def _advance_to_valid_hour(timestamp: int, scenario: Scenario, interval_seconds: int) -> int:
    current_ts = timestamp
    for _ in range(24 * 12 * 7):
        if scenario.applies_to_hour(_local_hour(current_ts)):
            return current_ts
        current_ts += interval_seconds
    raise RuntimeError(f"Khong tim duoc slot hop le cho scenario {scenario.name}")


def _estimate_interval_seconds(rows: list[dict[str, Any]]) -> int:
    timestamps = [int(item["timestamp"]) for item in rows]
    deltas = [right - left for left, right in zip(timestamps, timestamps[1:]) if right > left]
    if not deltas:
        return 900
    return max(60, int(statistics.median(deltas)))


def _build_slot_map(rows: list[dict[str, Any]], interval_seconds: int) -> dict[int, list[dict[str, Any]]]:
    slot_map: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        slot_no = int((int(row["timestamp"]) % 86400) // interval_seconds)
        slot_map.setdefault(slot_no, []).append(row)
    return slot_map


def _select_seed_row(
    slot_map: dict[int, list[dict[str, Any]]],
    seed_rows: list[dict[str, Any]],
    target_ts: int,
    interval_seconds: int,
) -> dict[str, Any]:
    slot_no = int((target_ts % 86400) // interval_seconds)
    candidates = slot_map.get(slot_no)
    if candidates:
        return candidates[-1]
    return seed_rows[-1]


def _clone_benchmark_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row[column] for column in BENCHMARK_COLUMNS}


def _sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    row["soil_temp"] = round(max(5.0, min(55.0, float(row["soil_temp"]))), 2)
    row["soil_humidity"] = round(max(0.0, min(99.99, float(row["soil_humidity"]))), 2)
    row["air_temp"] = round(max(5.0, min(55.0, float(row["air_temp"]))), 2)
    row["air_humidity"] = round(max(0.0, min(99.99, float(row["air_humidity"]))), 2)
    row["EC"] = round(max(0.0, float(row["EC"])), 1)
    row["pH"] = round(max(3.0, min(9.0, float(row["pH"]))), 2)
    row["N"] = round(max(0.0, float(row["N"])), 1)
    row["P"] = round(max(0.0, float(row["P"])), 1)
    row["K"] = round(max(0.0, float(row["K"])), 1)
    return row


def _phase_profile(progress: float) -> tuple[str, float]:
    progress = max(0.0, min(1.0, progress))
    if progress < 0.25:
        return "onset", 0.22 + (progress / 0.25) * 0.48
    if progress < 0.65:
        return "peak", 0.74 + ((progress - 0.25) / 0.40) * 0.26
    if progress < 0.85:
        return "stabilizing", 0.9 - ((progress - 0.65) / 0.20) * 0.16
    return "recovery", max(0.16, 0.74 - ((progress - 0.85) / 0.15) * 0.58)


def _build_labeled_row(
    benchmark_row: dict[str, Any],
    *,
    scenario_label: str,
    timeline_state: str,
    episode_id: str,
    phase_name: str,
    intensity: float,
    progress: float,
    effect_strength: float,
    source_seed_timestamp: int,
    record_present: int,
    system_context: str,
    recovery_hint: str,
) -> dict[str, Any]:
    labeled_row = dict(benchmark_row)
    labeled_row.update(
        {
            "scenario_label": scenario_label,
            "timeline_state": timeline_state,
            "episode_id": episode_id,
            "phase_name": phase_name,
            "is_synthetic": 1,
            "scenario_intensity": round(intensity, 4),
            "scenario_progress": round(progress, 4),
            "effect_strength": round(effect_strength, 4),
            "source_seed_timestamp": source_seed_timestamp,
            "record_present": record_present,
            "system_context": system_context,
            "recovery_hint": recovery_hint,
        }
    )
    return labeled_row


def _build_gap_row(
    *,
    timestamp: int,
    episode_id: str,
    intensity: float,
    progress: float,
    effect_strength: float,
    phase_name: str,
    source_seed_timestamp: int,
) -> dict[str, Any]:
    row = {column: None for column in BENCHMARK_COLUMNS}
    row["timestamp"] = timestamp
    recovery_hint = "sunlight_recovery_expected" if _local_hour(timestamp) < 6 or _local_hour(timestamp) >= 18 else "cloud_cover_recovery_possible"
    row.update(
        {
            "scenario_label": "packet_loss",
            "timeline_state": "outage",
            "episode_id": episode_id,
            "phase_name": phase_name,
            "is_synthetic": 1,
            "scenario_intensity": round(intensity, 4),
            "scenario_progress": round(progress, 4),
            "effect_strength": round(effect_strength, 4),
            "source_seed_timestamp": source_seed_timestamp,
            "record_present": 0,
            "system_context": "solar_power_outage",
            "recovery_hint": recovery_hint,
        }
    )
    return row


def _build_label_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"total": len(rows), "by_label": {}, "timeline_state_counts": {}}
    for row in rows:
        timeline_state = str(row["timeline_state"])
        summary["timeline_state_counts"][timeline_state] = summary["timeline_state_counts"].get(timeline_state, 0) + 1

        label = str(row["scenario_label"])
        stats = summary["by_label"].setdefault(
            label,
            {
                "count": 0,
                "event_row_count": 0,
                "missing_row_count": 0,
                "episode_count": 0,
                "episode_ids": set(),
                "min_timestamp": None,
                "max_timestamp": None,
                "avg_air_humidity": 0.0,
                "avg_soil_humidity": 0.0,
                "present_value_count": 0,
            },
        )
        stats["count"] += 1
        if row.get("episode_id"):
            stats["episode_ids"].add(str(row["episode_id"]))
        if int(row.get("record_present", 0)) == 0:
            stats["missing_row_count"] += 1
        else:
            stats["event_row_count"] += 1
            stats["avg_air_humidity"] += float(row["air_humidity"])
            stats["avg_soil_humidity"] += float(row["soil_humidity"])
            stats["present_value_count"] += 1

        timestamp = int(row["timestamp"])
        stats["min_timestamp"] = timestamp if stats["min_timestamp"] is None else min(stats["min_timestamp"], timestamp)
        stats["max_timestamp"] = timestamp if stats["max_timestamp"] is None else max(stats["max_timestamp"], timestamp)

    for label_stats in summary["by_label"].values():
        present_count = int(label_stats["present_value_count"])
        label_stats["episode_count"] = len(label_stats["episode_ids"])
        label_stats["episode_ids"] = sorted(label_stats["episode_ids"])
        label_stats["avg_air_humidity"] = 0.0 if present_count == 0 else round(label_stats["avg_air_humidity"] / present_count, 3)
        label_stats["avg_soil_humidity"] = 0.0 if present_count == 0 else round(label_stats["avg_soil_humidity"] / present_count, 3)
        del label_stats["present_value_count"]
    return summary


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _local_datetime(timestamp: int) -> datetime:
    return datetime.utcfromtimestamp(timestamp) + timedelta(hours=7)


def _local_hour(timestamp: int) -> int:
    return _local_datetime(timestamp).hour
