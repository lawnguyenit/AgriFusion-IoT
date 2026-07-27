from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tempfile

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile, ModelUnavailableError

try:
    from pytabkit.models.sklearn.sklearn_interfaces import RealMLP_TD_Classifier
except Exception as exc:  # pragma: no cover
    RealMLP_TD_Classifier = None
    REALMLP_IMPORT_ERROR = exc
else:  # pragma: no cover
    REALMLP_IMPORT_ERROR = None


def build_realmlp_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    if RealMLP_TD_Classifier is None:
        raise ModelUnavailableError(
            f"{type(REALMLP_IMPORT_ERROR).__name__}: {REALMLP_IMPORT_ERROR}"
            if REALMLP_IMPORT_ERROR is not None
            else "pytabkit RealMLP unavailable"
        )
    kwargs = dict(profile.hyperparameters)
    kwargs.setdefault("random_state", random_seed)
    kwargs.setdefault("n_threads", thread_count)
    kwargs.setdefault("n_cv", 1)
    kwargs.setdefault("n_refit", 0)
    kwargs.setdefault("val_fraction", 0.2)
    kwargs.setdefault("verbosity", 0)
    kwargs.setdefault("n_epochs", 16)
    kwargs.setdefault("batch_size", 256)
    kwargs.setdefault("tmp_folder", str(Path(tempfile.gettempdir()) / "agri_model_suite_pytabkit"))
    try:
        package_version = version("pytabkit")
    except PackageNotFoundError:  # pragma: no cover
        package_version = "UNKNOWN"
    return RealMLP_TD_Classifier(**kwargs), package_version
