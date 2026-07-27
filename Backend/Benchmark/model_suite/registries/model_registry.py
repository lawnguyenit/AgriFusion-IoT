from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from Backend.Benchmark.model_suite.contracts import ModelAdapterInfo, ModelProfile, ModelUnavailableError
from Backend.Benchmark.model_suite.families import (
    build_dummy_classifier,
    build_extra_trees_classifier,
    build_ft_transformer_classifier,
    build_logistic_regression_classifier,
    build_realmlp_classifier,
    build_tabpfn_classifier,
    build_xgboost_classifier,
)
from Backend.Benchmark.model_suite.registries.model_catalog import MODEL_CATALOG


ModelBuilder = Callable[[ModelProfile, int, int, int], tuple[object, str]]

MODEL_BUILDERS: dict[str, ModelBuilder] = {
    "dummy_majority": build_dummy_classifier,
    "logistic_regression": build_logistic_regression_classifier,
    "extra_trees": build_extra_trees_classifier,
    "xgboost": build_xgboost_classifier,
    "realmlp": build_realmlp_classifier,
    "ft_transformer": build_ft_transformer_classifier,
    "tabpfn": build_tabpfn_classifier,
}


def list_model_profiles() -> tuple[ModelProfile, ...]:
    return tuple(MODEL_CATALOG.values())


def resolve_model_profile(
    model_key: str,
    *,
    hyperparameter_overrides: dict[str, Any] | None = None,
    use_balanced_sample_weight: bool | None = None,
) -> ModelProfile:
    profile = MODEL_CATALOG.get(model_key)
    if profile is None:
        raise KeyError(f"Unknown model_key={model_key!r}.")
    return profile.with_overrides(
        hyperparameters=hyperparameter_overrides,
        use_balanced_sample_weight=use_balanced_sample_weight,
    )


def build_estimator(
    *,
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    builder = MODEL_BUILDERS.get(profile.model_key)
    if builder is None:
        raise KeyError(f"No builder registered for model_key={profile.model_key!r}.")
    return builder(profile, random_seed, thread_count, class_count)


def inspect_model_availability(
    model_key: str,
    *,
    random_seed: int = 20260717,
    thread_count: int = 1,
    class_count: int = 2,
) -> ModelAdapterInfo:
    profile = resolve_model_profile(model_key)
    try:
        build_estimator(
            profile=profile,
            random_seed=random_seed,
            thread_count=thread_count,
            class_count=class_count,
        )
    except ModelUnavailableError as exc:
        return ModelAdapterInfo(
            model_key=profile.model_key,
            family=profile.family,
            library=profile.library,
            available=False,
            note=f"{exc} | install_hint={_build_install_hint(profile.model_key, profile.library)}",
        )
    except Exception as exc:
        return ModelAdapterInfo(
            model_key=profile.model_key,
            family=profile.family,
            library=profile.library,
            available=False,
            note=f"{type(exc).__name__}: {exc} | install_hint={_build_install_hint(profile.model_key, profile.library)}",
        )
    return ModelAdapterInfo(
        model_key=profile.model_key,
        family=profile.family,
        library=profile.library,
        available=True,
        note=None,
    )


def inspect_models_availability(model_keys: Iterable[str]) -> tuple[ModelAdapterInfo, ...]:
    return tuple(inspect_model_availability(str(model_key)) for model_key in model_keys)


def assert_models_available(model_keys: Iterable[str]) -> tuple[ModelAdapterInfo, ...]:
    infos = inspect_models_availability(model_keys)
    unavailable = tuple(info for info in infos if not info.available)
    if unavailable:
        details = "; ".join(
            f"{info.model_key} [{info.library}]: {info.note}"
            for info in unavailable
        )
        raise ModelUnavailableError(f"Requested model(s) unavailable: {details}")
    return infos


def _build_install_hint(model_key: str, library: str) -> str:
    model_specific_hints = {
        "realmlp": "python -m pip install pytabkit",
        "ft_transformer": "python -m pip install pytabkit skorch",
        "tabpfn": "python -m pip install tabpfn and configure TABPFN_TOKEN or local model_path",
    }
    if model_key in model_specific_hints:
        return model_specific_hints[model_key]
    library_hints = {
        "scikit-learn": "python -m pip install scikit-learn",
        "xgboost": "python -m pip install xgboost",
        "pytabkit": "python -m pip install pytabkit",
        "tabpfn": "python -m pip install tabpfn and configure TABPFN_TOKEN or local model_path",
    }
    return library_hints.get(library, "install the required model library in the active environment")
