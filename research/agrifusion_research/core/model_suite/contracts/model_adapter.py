from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


class ModelUnavailableError(RuntimeError):
    """Raised when a requested model family is not available in the environment."""


@dataclass(frozen=True)
class ModelProfile:
    model_key: str
    display_name: str
    family: str
    library: str
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    enable_scaling: bool = True
    enable_variance_threshold: bool = True
    use_balanced_sample_weight: bool = False

    def with_overrides(
        self,
        *,
        hyperparameters: dict[str, Any] | None = None,
        use_balanced_sample_weight: bool | None = None,
    ) -> "ModelProfile":
        merged_hyperparameters = dict(self.hyperparameters)
        if hyperparameters:
            merged_hyperparameters.update(hyperparameters)
        return replace(
            self,
            hyperparameters=merged_hyperparameters,
            use_balanced_sample_weight=(
                self.use_balanced_sample_weight
                if use_balanced_sample_weight is None
                else bool(use_balanced_sample_weight)
            ),
        )


@dataclass(frozen=True)
class ModelAdapterInfo:
    model_key: str
    family: str
    library: str
    available: bool
    note: str | None = None
