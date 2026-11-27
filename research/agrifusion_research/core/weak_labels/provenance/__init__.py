"""Provenance and deterministic identity facade."""

from agrifusion_research.core.weak_labels.provenance.identities import canonicalize_payload, deterministic_id
from agrifusion_research.core.weak_labels.provenance.lineage import build_label_source_dependency, build_lineage_record
from agrifusion_research.core.weak_labels.provenance.release import (
    LABEL_RELEASE_SCHEMA_VERSION,
    build_label_release_manifest,
    materialize_label_release_frame,
)

build_deterministic_id = deterministic_id

__all__ = [
    "build_deterministic_id",
    "build_label_source_dependency",
    "build_lineage_record",
    "build_label_release_manifest",
    "materialize_label_release_frame",
    "LABEL_RELEASE_SCHEMA_VERSION",
    "canonicalize_payload",
    "deterministic_id",
]
