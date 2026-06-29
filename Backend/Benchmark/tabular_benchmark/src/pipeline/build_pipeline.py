from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.raw_tabular_dataset import build_raw_tabular_data_bundle
from Backend.Benchmark.tabular_benchmark.src.config.settings import DirectBenchmarkBuildConfig
from Backend.Benchmark.shared.artifacts import create_run_directory, write_json, write_text
from Backend.Benchmark.shared.labels import select_label_policy


def run_build_pipeline(config: DirectBenchmarkBuildConfig) -> dict[str, object]:
    config.validate()
    run_id, output_dir = create_run_directory(config.output_root, prefix="direct_build")
    experiments_dir = output_dir / "experiments"
    output_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    experiment_reports: list[dict[str, object]] = []
    print(
        f"[tabular_benchmark:build] label_mode={config.label_mode} run_id={run_id} output_dir={output_dir}"
    )
    for experiment_index, experiment_name in enumerate(config.experiments, start=1):
        print(
            f"[tabular_benchmark:build] experiment {experiment_index}/{len(config.experiments)} -> {experiment_name}"
        )
        experiment_output_dir = experiments_dir / experiment_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        experiment_reports.append(
            _build_single_experiment(
                config=config,
                experiment_name=experiment_name,
                output_dir=experiment_output_dir,
            )
        )

    manifest = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_mode": config.label_mode,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "experiments": config.experiments,
        "experiment_reports": experiment_reports,
    }
    write_json(output_dir / "dataset_manifest.json", manifest)
    write_json(output_dir / "run_config.json", config.to_dict())
    write_json(
        output_dir / "run_status.json",
        {
            "completed": True,
            "output_dir": str(output_dir),
            "label_mode": config.label_mode,
            "experiment_count": len(config.experiments),
        },
    )
    write_text(output_dir / "label_mode.txt", config.label_mode)
    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_mode": config.label_mode,
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "dataset_manifest.json"),
        "experiments": config.experiments,
    }


def _build_single_experiment(
    *,
    config: DirectBenchmarkBuildConfig,
    experiment_name: str,
    output_dir: Path,
) -> dict[str, object]:
    data_bundle = build_raw_tabular_data_bundle(config, experiment_name=experiment_name)
    dataframe = data_bundle.dataframe.copy()
    label_policy = select_label_policy(
        dataframe,
        requested_mode=config.label_mode,
        min_class_support=config.min_class_support,
        min_class_ratio=config.min_class_ratio,
        enforce_balance_for_explicit=False,
    )

    dataframe["selected_label_name"] = dataframe[label_policy.label_column]
    dataframe["selected_label_id"] = dataframe[label_policy.label_id_column]
    dataframe["direct_split"] = dataframe["split"]

    dataset_path = output_dir / "prepared_dataset.csv"
    dataframe.to_csv(dataset_path, index=False)
    write_json(
        output_dir / "feature_schema.json",
        {
            "experiment_name": experiment_name,
            "source_kind": data_bundle.source_kind,
            "feature_columns": list(data_bundle.feature_columns),
            "row_count": data_bundle.row_count,
            "split_counts": data_bundle.split_counts,
            "source_csvs": [str(path) for path in data_bundle.source_csvs],
        },
    )
    write_json(
        output_dir / "label_policy.json",
        {
            "selected_mode": label_policy.label_mode,
            "label_column": "selected_label_name",
            "label_id_column": "selected_label_id",
            "class_names": label_policy.class_names,
            "class_to_id": label_policy.class_to_id,
            "class_counts_train": label_policy.class_counts,
            "diagnostics": label_policy.diagnostics,
            "support_gate_enforced": False,
        },
    )
    split_summary = _split_label_summary(dataframe)
    write_json(output_dir / "split_label_summary.json", split_summary)
    write_json(output_dir / "split_policy.json", data_bundle.split_manifest)

    return {
        "experiment_name": experiment_name,
        "source_kind": data_bundle.source_kind,
        "dataset_path": str(dataset_path),
        "row_count": data_bundle.row_count,
        "split_counts": data_bundle.split_counts,
        "label_mode": label_policy.label_mode,
        "class_names": label_policy.class_names,
        "class_counts_train": label_policy.class_counts,
    }


def _split_label_summary(dataframe: pd.DataFrame) -> dict[str, object]:
    summary: dict[str, object] = {}
    for split_name in ["train", "validation", "test", "excluded_gap"]:
        split_frame = dataframe.loc[dataframe["split"] == split_name].copy()
        summary[split_name] = {
            "row_count": int(len(split_frame)),
            "selected_label_counts": {
                str(label): int(count)
                for label, count in split_frame["selected_label_name"].value_counts().sort_index().items()
            },
        }
    return summary
