from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ProtocolRegistry:
    run_dir: Path
    environment_manifest: pd.DataFrame
    visibility_policy_registry: pd.DataFrame
    experiment_arm_manifest: pd.DataFrame
    fold_policy_registry: pd.DataFrame
    e1_fold_registry: pd.DataFrame
    threshold_fit_cohort_manifest: pd.DataFrame
    future_target_policy: pd.DataFrame
    stage_registry: pd.DataFrame
    run_manifest: dict[str, object]


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    stage_id: str
    environment_id: str
    operation: str
    visibility_status: str
    reason: str
