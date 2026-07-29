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
    synthesis: Path
    ambiguity: Path
    collection_repair: Path

    def create(self) -> None:
        for path in (
            self.run_metadata,
            self.configs,
            self.manifests,
            self.audits,
            self.reports,
            self.synthesis,
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
        synthesis=root / "synthesis",
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
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "dependency_effects.parquet"),
            "role": "dependency_effects",
            "usage": "registered comparison effects computed only from preregistered pairs",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "dependency_stability_matrix.csv"),
            "role": "dependency_stability_matrix",
            "usage": "comparison x environment stability view for tranche-0 synthesis",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "dependency_classification.csv"),
            "role": "dependency_classification",
            "usage": "separate estimability and dependency classifications",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "estimability_matrix.csv"),
            "role": "estimability_matrix",
            "usage": "estimability states for preregistered comparisons",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "effect_uncertainty.csv"),
            "role": "effect_uncertainty",
            "usage": "descriptive uncertainty outputs for tranche-0 registered effects",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "claim_evidence_matrix.csv"),
            "role": "claim_evidence_matrix",
            "usage": "claim-level evidence statuses with supporting and contradicting artifacts",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "source_expansion_operational_effects.csv"),
            "role": "source_expansion_operational_effects",
            "usage": "operational source-expansion effect summary",
        },
        {
            "artifact_group": "synthesis",
            "path": str(layout.synthesis / "source_expansion_matched_budget_effects.csv"),
            "role": "source_expansion_matched_budget_effects",
            "usage": "matched-segment/day-budget source-expansion effect summary",
        },
        {
            "artifact_group": "ambiguity",
            "path": str(layout.ambiguity / "candidate_ambiguity_sets.yaml"),
            "role": "candidate_ambiguity_sets",
            "usage": "registered ambiguity candidates prior to evidence updates",
        },
        {
            "artifact_group": "ambiguity",
            "path": str(layout.ambiguity / "evidence_updated_ambiguity_sets.yaml"),
            "role": "evidence_updated_ambiguity_sets",
            "usage": "evidence-updated ambiguity statuses without causal promotion",
        },
        {
            "artifact_group": "ambiguity",
            "path": str(layout.ambiguity / "failure_attribution_matrix.csv"),
            "role": "failure_attribution_matrix",
            "usage": "claim-level ambiguity and evidence attribution table",
        },
        {
            "artifact_group": "ambiguity",
            "path": str(layout.ambiguity / "non_identifiability_report.md"),
            "role": "non_identifiability_report",
            "usage": "remaining ambiguity report and interpretation boundaries",
        },
    ]
