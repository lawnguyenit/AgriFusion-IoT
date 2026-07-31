"""Deterministic identity primitives for semantic artifacts."""

from Backend.Benchmark.weak_labels.contracts.native import canonicalize_payload, deterministic_id

build_deterministic_id = deterministic_id

__all__ = ["build_deterministic_id", "canonicalize_payload", "deterministic_id"]
