from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from Backend.Benchmark.context_classifier.src.config.settings import ContextClassifierConfig
from Backend.Benchmark.context_classifier.src.data.canonical_builder import (
    build_real_canonical,
    build_synthetic_canonical,
    write_label_summary,
)
from Backend.Benchmark.context_classifier.src.data.label_schemes import get_label_scheme
from Backend.Benchmark.context_classifier.src.data.sequence_builder import build_sequence_long
from Backend.Benchmark.context_classifier.src.data.splitting import split_real_dataset
from Backend.Benchmark.context_classifier.src.data.tabular_builder import (
    build_v0_tabular,
    build_v1_tabular,
    build_v2_tabular,
    build_v3_tabular,
)


def _write_json(payload: dict[str, object], output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _origin_slice(frame: pd.DataFrame, origin_name: str) -> pd.DataFrame:
    return frame.loc[frame["data_origin"] == origin_name].copy().reset_index(drop=True)


def run_build_pipeline(config: ContextClassifierConfig) -> dict[str, object]:
    config.validate()
    label_scheme = get_label_scheme(config.label_scheme)
    output_dir = config.make_run_dir()

    real_df = build_real_canonical(config.real_event_csv, config.label_scheme)
    synthetic_df = build_synthetic_canonical(config.synthetic_gap_aware_csv, config.label_scheme)
    split_real = split_real_dataset(
        real_df=real_df,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        purge_gap_minutes=config.purge_gap_minutes,
        split_strategy=config.split_strategy,
    )
    split_frames = {
        "train": pd.concat([split_real["train"], synthetic_df], ignore_index=True).sort_values(
            ["timestamp", "is_synthetic"]
        ).reset_index(drop=True),
        "validation": split_real["validation"].copy(),
        "test": split_real["test"].copy(),
    }
    canonical_df = pd.concat(
        [split_frames["train"], split_frames["validation"], split_frames["test"]],
        ignore_index=True,
    ).sort_values(["timestamp", "split_name", "is_synthetic"]).reset_index(drop=True)

    canonical_path = output_dir / "canonical_context_dataset.csv"
    real_canonical_path = output_dir / "real_canonical_labeled.csv"
    synthetic_canonical_path = output_dir / "synthetic_canonical_labeled.csv"
    label_summary_path = output_dir / "context_label_summary.json"
    real_label_summary_path = output_dir / "real_label_summary.json"
    synthetic_label_summary_path = output_dir / "synthetic_label_summary.json"
    run_config_path = output_dir / "run_config.json"
    manifest_path = output_dir / "dataset_manifest.json"
    splits_dir = output_dir / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)

    canonical_df.to_csv(canonical_path, index=False)
    real_df.to_csv(real_canonical_path, index=False)
    synthetic_df.to_csv(synthetic_canonical_path, index=False)
    write_label_summary(canonical_df, label_summary_path, config.label_scheme)
    write_label_summary(real_df, real_label_summary_path, config.label_scheme)
    write_label_summary(synthetic_df, synthetic_label_summary_path, config.label_scheme)
    _write_json(config.to_dict(), run_config_path)

    split_output_files: dict[str, dict[str, str]] = {}
    split_row_counts: dict[str, dict[str, int]] = {}
    total_sequence_rows = 0
    for split_name, split_df in split_frames.items():
        split_folder = splits_dir / split_name
        split_folder.mkdir(parents=True, exist_ok=True)
        split_canonical_path = split_folder / "canonical.csv"
        split_v0_path = split_folder / "tabular_v0.csv"
        split_v1_path = split_folder / "tabular_v1.csv"
        split_v2_path = split_folder / "tabular_v2.csv"
        split_v3_path = split_folder / "tabular_v3.csv"
        split_sequence_path = split_folder / "sequence_long.csv"
        split_real_only_path = split_folder / "canonical_real.csv"
        split_synthetic_only_path = split_folder / "canonical_synthetic.csv"

        v0_df = build_v0_tabular(split_df)
        v1_df = build_v1_tabular(split_df)
        v2_df = build_v2_tabular(split_df)
        v3_df = build_v3_tabular(split_df)
        sequence_df = build_sequence_long(split_df, config.sequence_lookback, config.sequence_stride)
        split_real_only_df = _origin_slice(split_df, "real")
        split_synthetic_only_df = _origin_slice(split_df, "synthetic")

        split_df.to_csv(split_canonical_path, index=False)
        split_real_only_df.to_csv(split_real_only_path, index=False)
        split_synthetic_only_df.to_csv(split_synthetic_only_path, index=False)
        v0_df.to_csv(split_v0_path, index=False)
        v1_df.to_csv(split_v1_path, index=False)
        v2_df.to_csv(split_v2_path, index=False)
        v3_df.to_csv(split_v3_path, index=False)
        sequence_df.to_csv(split_sequence_path, index=False)

        split_output_files[split_name] = {
            "canonical": str(split_canonical_path),
            "canonical_real": str(split_real_only_path),
            "canonical_synthetic": str(split_synthetic_only_path),
            "tabular_v0": str(split_v0_path),
            "tabular_v1": str(split_v1_path),
            "tabular_v2": str(split_v2_path),
            "tabular_v3": str(split_v3_path),
            "sequence_long": str(split_sequence_path),
        }
        split_row_counts[split_name] = {
            "canonical_row_count": int(len(split_df)),
            "v0_row_count": int(len(v0_df)),
            "v1_row_count": int(len(v1_df)),
            "v2_row_count": int(len(v2_df)),
            "v3_row_count": int(len(v3_df)),
            "sequence_row_count": int(len(sequence_df)),
            "synthetic_row_count": int((split_df["data_origin"] == "synthetic").sum()),
            "real_row_count": int((split_df["data_origin"] == "real").sum()),
        }
        total_sequence_rows += int(len(sequence_df))

    manifest = {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_scheme": label_scheme.name,
        "class_names": list(label_scheme.class_names),
        "label_scheme_description": label_scheme.description,
        "real_event_csv": str(config.real_event_csv),
        "synthetic_gap_aware_csv": str(config.synthetic_gap_aware_csv),
        "canonical_row_count": int(len(canonical_df)),
        "real_canonical_row_count": int(len(real_df)),
        "synthetic_canonical_row_count": int(len(synthetic_df)),
        "split_row_counts": split_row_counts,
        "sequence_row_count": total_sequence_rows,
        "sequence_lookback": config.sequence_lookback,
        "sequence_stride": config.sequence_stride,
        "train_ratio": config.train_ratio,
        "validation_ratio": config.validation_ratio,
        "test_ratio": config.test_ratio,
        "purge_gap_minutes": config.purge_gap_minutes,
        "split_strategy": config.split_strategy,
        "output_files": {
            "canonical": str(canonical_path),
            "real_canonical": str(real_canonical_path),
            "synthetic_canonical": str(synthetic_canonical_path),
            "splits": split_output_files,
            "label_summary": str(label_summary_path),
            "real_label_summary": str(real_label_summary_path),
            "synthetic_label_summary": str(synthetic_label_summary_path),
            "run_config": str(run_config_path),
        },
        "assumptions": [
            "Real data duoc chia train/validation/test theo thoi gian truoc khi dua synthetic vao train.",
            "Synthetic chi nam trong split train; validation va test la real-only.",
            "v0/v1/v2/v3 duoc build rieng cho tung split de tranh leakage qua ranh gioi train/validation/test.",
            "v0 = raw full, v1 = raw core, v2 = v1 + delta_1step + 3h slope/range/mean, v3 = v2 + 8h slope/range/mean.",
            "TabNet, FT-Transformer, TabPFN, va XGBoost se dung tabular_v0/tabular_v1/tabular_v2/tabular_v3 cua tung split.",
            "LSTM se dung sequence_long cua tung split va tu tensorize o buoc train sau.",
            f"Label scheme hien tai la {label_scheme.name}.",
        ],
    }
    _write_json(manifest, manifest_path)

    return {
        "benchmark_family": config.benchmark_family,
        "benchmark_version": config.benchmark_version,
        "label_scheme": label_scheme.name,
        "canonical_row_count": int(len(canonical_df)),
        "sequence_row_count": total_sequence_rows,
        "tabular_outputs": split_output_files,
        "output_dir": str(output_dir),
    }
