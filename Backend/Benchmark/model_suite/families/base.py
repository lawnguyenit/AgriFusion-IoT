from __future__ import annotations

from collections.abc import Callable

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile


ModelBuilder = Callable[[ModelProfile, int, int, int], tuple[object, str]]
