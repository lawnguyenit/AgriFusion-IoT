from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidityLifecycleArtifactLayout:
    root: Path
    run_metadata: Path
    configs: Path
    manifests: Path
    audits: Path
    reports: Path
    ambiguity: Path
    collection_repair: Path

    def create(self) -> None:
        for path in (
            self.run_metadata,
            self.configs,
            self.manifests,
            self.audits,
            self.reports,
            self.ambiguity,
            self.collection_repair,
        ):
            path.mkdir(parents=True, exist_ok=True)


def build_validity_lifecycle_layout(root: Path) -> ValidityLifecycleArtifactLayout:
    return ValidityLifecycleArtifactLayout(
        root=root,
        run_metadata=root / "run_metadata",
        configs=root / "configs",
        manifests=root / "manifests",
        audits=root / "audits",
        reports=root / "reports",
        ambiguity=root / "ambiguity",
        collection_repair=root / "collection_repair",
    )


def build_artifact_catalog(layout: ValidityLifecycleArtifactLayout) -> list[dict[str, str]]:
    return [
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "run_manifest.json"),
            "role": "run_reproducibility",
            "usage": "linked protocol inputs and lifecycle run provenance",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "validity_lifecycle_validation.json"),
            "role": "validation_summary",
            "usage": "machine-readable lifecycle gate output",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "artifact_catalog.csv"),
            "role": "artifact_index",
            "usage": "single-file index of lifecycle outputs",
        },
        {
            "artifact_group": "manifests",
            "path": str(layout.manifests / "observation_registry.parquet"),
            "role": "observation_registry",
            "usage": "sample-level lifecycle registry aligned to E1/E2/E3",
        },
        {
            "artifact_group": "manifests",
            "path": str(layout.manifests / "view_observation_registry.parquet"),
            "role": "view_observation_registry",
            "usage": "per-view lifecycle registry used by support and eligibility audits",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "environment_support_matrix.csv"),
            "role": "support_audit",
            "usage": "environment x view x class support status",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "environment_eligibility_matrix.csv"),
            "role": "eligibility_audit",
            "usage": "3h/8h eligibility loss by environment, view, and class",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "environment_continuity_matrix.csv"),
            "role": "continuity_audit",
            "usage": "day and segment continuity summaries across environments",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "label_first_occurrence.csv"),
            "role": "label_first_occurrence",
            "usage": "explains whether absent labels have appeared before a given environment",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "class_day_segment_support.csv"),
            "role": "linear_split_support",
            "usage": "chronological 70/15/15 label presence by environment and view",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "comparison_hash_audit.csv"),
            "role": "matched_comparison_integrity",
            "usage": "verifies left/right matched cohorts stay aligned",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "ec_npk_dependency.csv"),
            "role": "proxy_dependency_audit",
            "usage": "quantifies whether N/P/K proxies are deterministic functions of EC",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "ph_measurement_stability.csv"),
            "role": "ph_stability_audit",
            "usage": "quantifies pH range stability and relocation changes",
        },
        {
            "artifact_group": "reports",
            "path": str(layout.reports / "validity_lifecycle_audit_report.md"),
            "role": "human_report",
            "usage": "English lifecycle report with stage readiness answers",
        },
    ]
