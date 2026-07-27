from __future__ import annotations

from Backend.Benchmark.model_suite.contracts.run_spec import ModelSuiteRunSpec


def build_run_manifest(spec: ModelSuiteRunSpec) -> dict[str, object]:
    return {
        "run_id": spec.run_id,
        "profile_name": spec.profile_name,
        "protocol_run_dir": str(spec.protocol_source.protocol_run_dir),
        "runner_dir": str(spec.protocol_source.runner_dir),
        "model_keys": list(spec.model_keys),
        "stage_ids": [str(stage_spec["stage_id"]) for stage_spec in spec.stage_specs],
        "output_dir": str(spec.output_dir),
        "metadata": spec.metadata,
    }
