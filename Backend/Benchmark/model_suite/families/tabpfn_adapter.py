from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile, ModelUnavailableError

try:
    from tabpfn import TabPFNClassifier
except Exception as exc:  # pragma: no cover
    TabPFNClassifier = None
    TABPFN_IMPORT_ERROR = exc
else:  # pragma: no cover
    TABPFN_IMPORT_ERROR = None


def build_tabpfn_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    if TabPFNClassifier is None:
        raise ModelUnavailableError(
            f"{type(TABPFN_IMPORT_ERROR).__name__}: {TABPFN_IMPORT_ERROR}"
            if TABPFN_IMPORT_ERROR is not None
            else "tabpfn unavailable"
        )
    kwargs = dict(profile.hyperparameters)
    model_path = kwargs.get("model_path", "auto")
    token_present = bool(os.environ.get("TABPFN_TOKEN"))
    if not token_present and model_path == "auto":
        raise ModelUnavailableError(
            "TabPFN requires TABPFN license acceptance and a TABPFN_TOKEN for auto weight download "
            "in this non-interactive environment, or an explicit local model_path."
        )
    kwargs.setdefault("random_state", random_seed)
    kwargs.setdefault("n_preprocessing_jobs", thread_count)
    kwargs.setdefault("show_progress_bar", False)
    kwargs.setdefault("device", "auto")
    try:
        package_version = version("tabpfn")
    except PackageNotFoundError:  # pragma: no cover
        package_version = "UNKNOWN"
    return TabPFNClassifier(**kwargs), package_version
