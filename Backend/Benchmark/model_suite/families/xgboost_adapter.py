from __future__ import annotations

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile, ModelUnavailableError

try:
    import xgboost as xgb  # type: ignore
except Exception as exc:  # pragma: no cover
    xgb = None
    XGBOOST_IMPORT_ERROR = exc
else:  # pragma: no cover
    XGBOOST_IMPORT_ERROR = None


def build_xgboost_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    if xgb is None:
        raise ModelUnavailableError(
            f"{type(XGBOOST_IMPORT_ERROR).__name__}: {XGBOOST_IMPORT_ERROR}"
            if XGBOOST_IMPORT_ERROR is not None
            else "xgboost unavailable"
        )
    kwargs = dict(profile.hyperparameters)
    kwargs.setdefault("random_state", random_seed)
    kwargs.setdefault("n_jobs", thread_count)
    kwargs.setdefault("eval_metric", "logloss" if class_count == 2 else "mlogloss")
    kwargs.setdefault("objective", "binary:logistic" if class_count == 2 else "multi:softprob")
    if class_count > 2:
        kwargs.setdefault("num_class", class_count)
    return xgb.XGBClassifier(**kwargs), xgb.__version__
