from __future__ import annotations

from typing import Any

__all__ = ["materialize_dataset_views"]


def __getattr__(name: str) -> Any:
    if name == "materialize_dataset_views":
        from .pipelines.materialize import materialize_dataset_views

        return materialize_dataset_views
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
