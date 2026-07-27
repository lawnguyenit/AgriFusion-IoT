from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tempfile

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile, ModelUnavailableError

try:
    from pytabkit.models.sklearn.sklearn_interfaces import FTT_D_Classifier
except Exception as exc:  # pragma: no cover
    FTT_D_Classifier = None
    FT_TRANSFORMER_IMPORT_ERROR = exc
else:  # pragma: no cover
    FT_TRANSFORMER_IMPORT_ERROR = None


def build_ft_transformer_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    if FTT_D_Classifier is None:
        raise ModelUnavailableError(
            f"{type(FT_TRANSFORMER_IMPORT_ERROR).__name__}: {FT_TRANSFORMER_IMPORT_ERROR}"
            if FT_TRANSFORMER_IMPORT_ERROR is not None
            else "pytabkit FT-Transformer unavailable"
        )
    _assert_ft_transformer_runtime_dependencies()
    kwargs = dict(profile.hyperparameters)
    kwargs.setdefault("random_state", random_seed)
    kwargs.setdefault("n_threads", thread_count)
    kwargs.setdefault("n_cv", 1)
    kwargs.setdefault("n_refit", 0)
    kwargs.setdefault("val_fraction", 0.2)
    kwargs.setdefault("verbosity", 0)
    kwargs.setdefault("verbose", 0)
    kwargs.setdefault("max_epochs", 16)
    kwargs.setdefault("batch_size", 256)
    kwargs.setdefault("use_checkpoints", False)
    kwargs.setdefault("tmp_folder", str(Path(tempfile.gettempdir()) / "agri_model_suite_pytabkit"))
    try:
        package_version = version("pytabkit")
    except PackageNotFoundError:  # pragma: no cover
        package_version = "UNKNOWN"
    return FTT_D_Classifier(**kwargs), package_version


def _assert_ft_transformer_runtime_dependencies() -> None:
    try:
        import skorch  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise ModelUnavailableError(f"{type(exc).__name__}: {exc}") from exc
    try:
        from pytabkit.models.nn_models.rtdl_resnet import create_ft_transformer_classifier_skorch  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise ModelUnavailableError(f"{type(exc).__name__}: {exc}") from exc
