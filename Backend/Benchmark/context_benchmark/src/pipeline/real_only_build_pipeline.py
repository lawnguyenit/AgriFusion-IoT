from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from Backend.Benchmark.context_benchmark.src.data.canonical_builder import write_label_summary
from Backend.Benchmark.context_benchmark.src.data.tabular_builder import (
    build_v0_tabular,
    build_v1_tabular,
    build_v2_tabular,
    build_v3_tabular,
)
from Backend.Benchmark.context_benchmark.src.data.sequence_builder import build_sequence_long
from Backend.Benchmark.context_benchmark.src.data.training_io import load_build_manifest
from Backend.Benchmark.shared.artifacts import create_run_directory


def _write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required split file not found: {path}")
    return pd.read_csv(path)


def _empty_like(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.iloc[0:0].copy().reset_index(drop=True)


def _default_real_only_output_root(source_build_run_dir: Path) -> Path:
    context_benchmark_root = source_build_run_dir.parents[4] if source_build_run_dir.parent.name in {"augmented", "real_only"} else source_build_run_dir.parents[2]
    source_manifest = load_build_manifest(source_build_run_dir)
    source_label_scheme = str(source_manifest.get("label_scheme", "four_class"))
    return (context_benchmark_root / "artifacts" / "builds" / source_label_scheme / "real_only").resolve()


def _make_run_dir(output_root: Path) -> Path:
    _, run_dir = create_run_directory(output_root, prefix="context_build_real_only")
    return run_dir


def run_real_only_build_pipeline(
    *,
    source_build_run_dir: Path,
    output_root: Path | None = None,
) -> dict[str, object]:
    source_build_run_dir = source_build_run_dir.resolve()
    source_manifest = load_build_manifest(source_build_run_dir)
    label_scheme = str(source_manifest.get("label_scheme", "four_class"))
    if output_root is None:
        output_root = _default_real_only_output_root(source_build_run_dir)
    else:
        output_root = output_root.resolve()
    output_dir = _make_run_dir(output_root)

    train_real_df = _load_csv(source_build_run_dir / "splits" / "train" / "canonical_real.csv")
    validation_df = _load_csv(source_build_run_dir / "splits" / "validation" / "canonical.csv")
    test_df = _load_csv(source_build_run_dir / "splits" / "test" / "canonical.csv")

    train_df = train_real_df.copy().reset_index(drop=True)
    validation_df = validation_df.copy().reset_index(drop=True)
    test_df = test_df.copy().reset_index(drop=True)
    synthetic_df = _empty_like(train_df)
    canonical_df = pd.concat([train_df, validation_df, test_df], ignore_index=True).sort_values(
        ["timestamp", "split_name", "is_synthetic"],
        kind="stable",
    ).reset_index(drop=True)

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
    canonical_df.to_csv(real_canonical_path, index=False)
    synthetic_df.to_csv(synthetic_canonical_path, index=False)
    write_label_summary(canonical_df, label_summary_path, label_scheme)
    write_label_summary(canonical_df, real_label_summary_path, label_scheme)
    write_label_summary(synthetic_df, synthetic_label_summary_path, label_scheme)
    _write_json(
        {
            "mode": "real_only_from_existing_build",
            "label_scheme": label_scheme,
            "source_build_run_dir": str(source_build_run_dir),
            "source_manifest_path": str(source_build_run_dir / "dataset_manifest.json"),
            "output_root": str(output_root),
        },
        run_config_path,
    )

    split_frames = {
        "train": train_df,
        "validation": validation_df,
        "test": test_df,
    }
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
        sequence_df = build_sequence_long(split_df, int(source_manifest.get("sequence_lookback", 12)), int(source_manifest.get("sequence_stride", 1)))
        split_synthetic_only_df = _empty_like(split_df)

        split_df.to_csv(split_canonical_path, index=False)
        split_df.to_csv(split_real_only_path, index=False)
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
            "synthetic_row_count": 0,
            "real_row_count": int(len(split_df)),
        }
        total_sequence_rows += int(len(sequence_df))

    manifest = {
        "benchmark_family": source_manifest.get("benchmark_family", "context_benchmark"),
        "benchmark_version": "dataset_builder_real_only_v1",
        "label_scheme": label_scheme,
        "class_names": list(source_manifest.get("class_names", [])),
        "label_scheme_description": source_manifest.get("label_scheme_description", ""),
        "real_event_csv": source_manifest.get("real_event_csv"),
        "synthetic_gap_aware_csv": None,
        "source_build_run_dir": str(source_build_run_dir),
        "source_synthetic_gap_aware_csv": source_manifest.get("synthetic_gap_aware_csv"),
        "canonical_row_count": int(len(canonical_df)),
        "real_canonical_row_count": int(len(canonical_df)),
        "synthetic_canonical_row_count": 0,
        "split_row_counts": split_row_counts,
        "sequence_row_count": total_sequence_rows,
        "sequence_lookback": int(source_manifest.get("sequence_lookback", 12)),
        "sequence_stride": int(source_manifest.get("sequence_stride", 1)),
        "train_ratio": source_manifest.get("train_ratio"),
        "validation_ratio": source_manifest.get("validation_ratio"),
        "test_ratio": source_manifest.get("test_ratio"),
        "purge_gap_minutes": source_manifest.get("purge_gap_minutes"),
        "split_strategy": source_manifest.get("split_strategy"),
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
            "Train/validation/test trong build nay deu la real-only; khong chen synthetic vao train split.",
            "Validation va test duoc tai su dung nguyen xi tu source build run.",
            "Train split duoc lay tu canonical_real.csv cua source build run de loai augmentation ma khong doi logic split real.",
            "v0/v1/v2/v3 duoc rebuild lai tu cac split real-only nay.",
            "sequence_long duoc giu lai chi de backward-compatible voi artifact cu; train active hien tai la tabular-only.",
        ],
    }
    _write_json(manifest, manifest_path)

    return {
        "benchmark_family": manifest["benchmark_family"],
        "benchmark_version": manifest["benchmark_version"],
        "label_scheme": label_scheme,
        "canonical_row_count": int(len(canonical_df)),
        "sequence_row_count": total_sequence_rows,
        "tabular_outputs": split_output_files,
        "output_dir": str(output_dir),
        "source_build_run_dir": str(source_build_run_dir),
    }
