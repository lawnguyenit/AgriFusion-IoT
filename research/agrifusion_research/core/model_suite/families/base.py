from __future__ import annotations

from collections.abc import Callable

from agrifusion_research.core.model_suite.contracts.model_adapter import ModelProfile


ModelBuilder = Callable[[ModelProfile, int, int, int], tuple[object, str]]
