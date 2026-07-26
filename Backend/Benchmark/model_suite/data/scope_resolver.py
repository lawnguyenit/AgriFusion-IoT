from __future__ import annotations

from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import (
    build_frozen_target_run_frames as _build_frozen_target_run_frames,
)
from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import build_stage_run_frames as _build_stage_run_frames
from Backend.Benchmark.model_suite.utils.config_loader import load_json_yaml


def load_stage_specs_for_profile(config_path, profile_name: str) -> tuple[dict[str, object], ...]:
    payload = load_json_yaml(config_path)
    profiles = payload.get("profiles", {})
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise KeyError(f"Unknown training profile: {profile_name}")
    stage_specs = profile.get("stage_specs", [])
    if not isinstance(stage_specs, list):
        raise ValueError(f"training profile {profile_name} stage_specs must be a list.")
    return tuple(stage_specs)


def list_training_profiles(config_path) -> tuple[dict[str, object], ...]:
    payload = load_json_yaml(config_path)
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("training profile config must expose an object at profiles.")
    rows: list[dict[str, object]] = []
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        rows.append(
            {
                "profile_name": str(profile_name),
                "description": str(profile.get("description", "")),
                "stage_count": int(len(profile.get("stage_specs", []))),
            }
        )
    return tuple(rows)


def build_stage_run_frames(
    *,
    stage_spec: dict[str, object],
    task_training_manifest,
    comparison_training_manifest,
    frozen_target_manifest=None,
):
    source_kind = str(stage_spec.get("source_kind", "task_and_comparison"))
    if source_kind == "frozen_target":
        if frozen_target_manifest is None:
            raise ValueError("frozen_target_manifest is required for frozen_target stage specs.")
        feature_view_ids = tuple(str(value) for value in stage_spec.get("feature_views", []))
        run_frames, validation_rows = _build_frozen_target_run_frames(
            frozen_target_manifest,
            feature_view_ids=feature_view_ids,
        )
        stage_id = str(stage_spec["stage_id"])
        for row in validation_rows:
            row["stage_id"] = stage_id
        for run_frame in run_frames:
            run_frame["stage_id"] = stage_id
        return run_frames, validation_rows
    return _build_stage_run_frames(
        stage_spec=stage_spec,
        task_training_manifest=task_training_manifest,
        comparison_training_manifest=comparison_training_manifest,
    )
