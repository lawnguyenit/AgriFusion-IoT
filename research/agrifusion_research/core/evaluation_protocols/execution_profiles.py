"""Explicit environment scopes for governed evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class EvaluationExecutionProfile:
    profile_id: str
    protocol_stage_id: str
    label_apply_environment_ids: tuple[str, ...]
    train_environment_ids: tuple[str, ...]
    evaluation_environment_ids: tuple[str, ...]
    target_environment_ids: tuple[str, ...]

    @property
    def read_environment_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            self.label_apply_environment_ids
            + self.train_environment_ids
            + self.evaluation_environment_ids
            + self.target_environment_ids
        ))

    @classmethod
    def load(cls, path: Path) -> "EvaluationExecutionProfile":
        resolved = path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Evaluation execution profile is missing: {resolved}")
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Evaluation execution profile must be a YAML mapping.")

        def ids(key: str) -> tuple[str, ...]:
            value = payload.get(key, [])
            if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
                raise ValueError(f"Execution profile field {key!r} must be a non-empty list.")
            return tuple(dict.fromkeys(str(item) for item in value))

        target_value = payload.get("target_environment_ids", [])
        if not isinstance(target_value, list) or any(not str(item).strip() for item in target_value):
            raise ValueError("Execution profile field 'target_environment_ids' must be a list.")
        profile = cls(
            profile_id=str(payload.get("profile_id", "")).strip(),
            protocol_stage_id=str(payload.get("protocol_stage_id", "")).strip(),
            label_apply_environment_ids=ids("label_apply_environment_ids"),
            train_environment_ids=ids("train_environment_ids"),
            evaluation_environment_ids=ids("evaluation_environment_ids"),
            target_environment_ids=tuple(dict.fromkeys(str(item) for item in target_value)),
        )
        if not profile.profile_id or not profile.protocol_stage_id:
            raise ValueError("Execution profile requires profile_id and protocol_stage_id.")
        if not set(profile.train_environment_ids).issubset(profile.label_apply_environment_ids):
            raise ValueError("Train environments must be a subset of label-apply environments.")
        if not set(profile.target_environment_ids).issubset(profile.evaluation_environment_ids):
            raise ValueError("Target environments must be a subset of evaluation environments.")
        return profile


def default_full_profile() -> EvaluationExecutionProfile:
    """Compatibility profile matching the historical P1/P2 runner scope."""
    return EvaluationExecutionProfile(
        profile_id="FULL_P1_P2_RQ2B_V1",
        protocol_stage_id="RQ2B_E3_REEVALUATION_BATCH",
        label_apply_environment_ids=("E1", "E2", "E3_TARGET_PREEXPOSED"),
        train_environment_ids=("E1", "E2"),
        evaluation_environment_ids=("E1", "E2", "E3_TARGET_PREEXPOSED"),
        target_environment_ids=("E3_TARGET_PREEXPOSED",),
    )
