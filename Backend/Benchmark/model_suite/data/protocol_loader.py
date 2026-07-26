from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.model_suite.contracts.run_spec import ProtocolSourceRef
from .validators import assert_protocol_runner_ready


@dataclass(frozen=True)
class LoadedProtocolRunner:
    source_ref: ProtocolSourceRef
    task_registry: pd.DataFrame
    task_manifest: pd.DataFrame
    comparison_manifest: pd.DataFrame
    frozen_target_manifest: pd.DataFrame


def load_protocol_runner(protocol_run_dir: Path) -> LoadedProtocolRunner:
    runner_dir = protocol_run_dir / "primary_protocol" / "runner"
    source_ref = ProtocolSourceRef(
        protocol_run_dir=protocol_run_dir.resolve(),
        runner_dir=runner_dir.resolve(),
        task_registry_path=(runner_dir / "task_view_registry.csv").resolve(),
        task_manifest_path=(runner_dir / "task_training_manifest.parquet").resolve(),
        comparison_manifest_path=(runner_dir / "comparison_training_manifest.parquet").resolve(),
        frozen_target_manifest_path=(runner_dir / "frozen_target_manifest.parquet").resolve(),
    )
    assert_protocol_runner_ready(source_ref)
    return LoadedProtocolRunner(
        source_ref=source_ref,
        task_registry=pd.read_csv(source_ref.task_registry_path).convert_dtypes(),
        task_manifest=pd.read_parquet(source_ref.task_manifest_path).convert_dtypes(),
        comparison_manifest=pd.read_parquet(source_ref.comparison_manifest_path).convert_dtypes(),
        frozen_target_manifest=pd.read_parquet(source_ref.frozen_target_manifest_path).convert_dtypes(),
    )
