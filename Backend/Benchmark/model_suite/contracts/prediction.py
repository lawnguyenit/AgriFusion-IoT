from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPredictionRecord:
    stage_id: str
    model_key: str
    run_scope: str
    feature_view_id: str
    fold_id: str
    partition: str
    sample_id: str
    label_name_true: str
    label_name_pred: str
