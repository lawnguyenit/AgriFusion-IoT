from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.benchmark_dataset.single_window_features.src.config import SATURATION_THRESHOLD
from Backend.Benchmark.benchmark_dataset.single_window_features.src.experiments import SingleWindowExperimentSpec, build_experiment_specs
from Backend.Benchmark.benchmark_dataset.single_window_features.src.io import load_layer1_frame, resolve_input_csv, resolve_output_dir, write_single_window_csv
from Backend.Core.layer2 import Layer2FeatureConfig, build_layer2_feature_bundle


@dataclass(frozen=True)
class SingleWindowBuildResult:
    experiment_name: str
    input_csv: Path
    output_csv: Path
    row_count: int
    columns: list[str]


def build_single_window_experiments(
    input_csv: Path | None = None,
    output_dir: Path | None = None,
    experiment_names: list[str] | None = None,
) -> list[SingleWindowBuildResult]:
    source_csv = resolve_input_csv(input_csv)
    target_dir = resolve_output_dir(output_dir)
    specs = build_experiment_specs()
    selected_specs = _select_specs(specs, experiment_names)

    base_frame = load_layer1_frame(source_csv)
    bundle = build_layer2_feature_bundle(
        base_frame,
        config=Layer2FeatureConfig(air_humidity_saturation_threshold=SATURATION_THRESHOLD),
    )

    results: list[SingleWindowBuildResult] = []
    for spec in selected_specs:
        output_csv = target_dir / spec.output_filename
        export_frame = bundle.dataframe[spec.feature_columns].copy()
        export_frame = _filter_incomplete_rows(spec, export_frame)
        export_frame = _append_train_label_columns(export_frame, base_frame)
        write_single_window_csv(export_frame, output_csv)
        results.append(
            SingleWindowBuildResult(
                experiment_name=spec.name,
                input_csv=source_csv,
                output_csv=output_csv,
                row_count=len(export_frame),
                columns=list(export_frame.columns),
            )
        )
    return results


def _select_specs(
    specs: dict[str, SingleWindowExperimentSpec],
    experiment_names: list[str] | None,
) -> list[SingleWindowExperimentSpec]:
    if not experiment_names:
        return [specs[name] for name in ("exp1", "exp2", "exp3", "exp4", "exp5", "exp6")]
    return [specs[name] for name in experiment_names]


def _append_train_label_columns(export_frame: pd.DataFrame, source_frame: pd.DataFrame) -> pd.DataFrame:
    if "big_label" not in source_frame.columns:
        return export_frame
    labeled = export_frame.copy()
    labeled["big_label"] = source_frame.loc[labeled.index, "big_label"].fillna("none").astype(str)
    return labeled


def _filter_incomplete_rows(spec: SingleWindowExperimentSpec, export_frame: pd.DataFrame) -> pd.DataFrame:
    if spec.name != "exp2":
        return export_frame
    valid_mask = export_frame.notna().all(axis=1)
    return export_frame.loc[valid_mask].copy()
