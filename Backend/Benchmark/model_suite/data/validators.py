from __future__ import annotations

from Backend.Benchmark.model_suite.contracts.run_spec import ProtocolSourceRef


def assert_protocol_runner_ready(source_ref: ProtocolSourceRef) -> None:
    missing_paths = [
        path
        for path in (
            source_ref.protocol_run_dir,
            source_ref.runner_dir,
            source_ref.task_registry_path,
            source_ref.task_manifest_path,
            source_ref.comparison_manifest_path,
            source_ref.frozen_target_manifest_path,
        )
        if not path.exists()
    ]
    if missing_paths:
        rendered = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(f"Protocol runner inputs are missing: {rendered}")
