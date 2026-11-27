from __future__ import annotations


def resolve_smoke_hyperparameters(model_key: str) -> dict[str, object]:
    if model_key == "xgboost":
        return {"n_estimators": 64, "max_depth": 4, "learning_rate": 0.1}
    return {}
