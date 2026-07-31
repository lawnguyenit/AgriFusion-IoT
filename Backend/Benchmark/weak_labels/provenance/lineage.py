"""Lineage records for label-source dependencies."""

from Backend.Benchmark.weak_labels.provenance.engine_lineage import (
    build_label_source_dependency,
    validate_referential_integrity,
)

build_lineage_record = build_label_source_dependency

__all__ = [
    "build_label_source_dependency",
    "build_lineage_record",
    "validate_referential_integrity",
]
