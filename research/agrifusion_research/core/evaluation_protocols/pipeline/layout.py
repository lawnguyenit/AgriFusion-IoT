from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationArtifactLayout:
    root: Path
    run_metadata: Path
    domain_manifests: Path
    validity_diagnostics: Path
    validity_representation: Path
    validity_evaluation: Path
    primary_protocol: Path
    primary_folds: Path
    primary_cohorts: Path
    primary_lineage: Path
    primary_runner: Path
    temporal_diagnostics: Path
    support_5day: Path
    support_7day: Path
    v2_coverage: Path
    transport_diagnostics: Path
    transport_feature_shift: Path
    transport_label_shift: Path
    threshold_diagnostics: Path
    threshold_policy: Path
    threshold_transport: Path
    dependency_manifests: Path

    def create(self) -> None:
        for path in (
            self.run_metadata,
            self.domain_manifests,
            self.validity_diagnostics,
            self.validity_representation,
            self.validity_evaluation,
            self.primary_protocol,
            self.primary_folds,
            self.primary_cohorts,
            self.primary_lineage,
            self.primary_runner,
            self.temporal_diagnostics,
            self.support_5day,
            self.support_7day,
            self.v2_coverage,
            self.transport_diagnostics,
            self.transport_feature_shift,
            self.transport_label_shift,
            self.threshold_diagnostics,
            self.threshold_policy,
            self.threshold_transport,
            self.dependency_manifests,
        ):
            path.mkdir(parents=True, exist_ok=True)


def build_evaluation_artifact_layout(root: Path) -> EvaluationArtifactLayout:
    return EvaluationArtifactLayout(
        root=root,
        run_metadata=root / "run_metadata",
        domain_manifests=root / "domain_manifests",
        validity_diagnostics=root / "validity_diagnostics",
        validity_representation=root / "validity_diagnostics" / "representation",
        validity_evaluation=root / "validity_diagnostics" / "evaluation",
        primary_protocol=root / "primary_protocol",
        primary_folds=root / "primary_protocol" / "folds",
        primary_cohorts=root / "primary_protocol" / "cohorts",
        primary_lineage=root / "primary_protocol" / "lineage",
        primary_runner=root / "primary_protocol" / "runner",
        temporal_diagnostics=root / "temporal_diagnostics",
        support_5day=root / "temporal_diagnostics" / "support_5day",
        support_7day=root / "temporal_diagnostics" / "secondary_7day",
        v2_coverage=root / "temporal_diagnostics" / "v2_coverage",
        transport_diagnostics=root / "transport_diagnostics",
        transport_feature_shift=root / "transport_diagnostics" / "feature_shift",
        transport_label_shift=root / "transport_diagnostics" / "label_shift",
        threshold_diagnostics=root / "threshold_diagnostics",
        threshold_policy=root / "threshold_diagnostics" / "policy",
        threshold_transport=root / "threshold_diagnostics" / "transport",
        dependency_manifests=root / "dependency_manifests",
    )


def build_artifact_catalog(layout: EvaluationArtifactLayout) -> list[dict[str, str]]:
    return [
        {
            "artifact_group": "run_metadata",
            "path": str(layout.root / "ARTIFACT_GUIDE.md"),
            "role": "artifact_guide",
            "usage": "reader-first overview of what this run takes in, does, and writes out",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "run_manifest.json"),
            "role": "run_reproducibility",
            "usage": "primary metadata for rerun and provenance",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "protocol_validation_report.json"),
            "role": "validation_summary",
            "usage": "human-readable gate summary and caveats",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "artifact_catalog.csv"),
            "role": "artifact_index",
            "usage": "single-file map of authoritative outputs",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "README.md"),
            "role": "run_metadata_guide",
            "usage": "short explanation of what run_metadata contains",
        },
        {
            "artifact_group": "domain_manifests",
            "path": str(layout.domain_manifests / "deployment_domains.csv"),
            "role": "domain_boundary_manifest",
            "usage": "maps canonical rows to P1/P2 protocol domains",
        },
        {
            "artifact_group": "domain_manifests",
            "path": str(layout.domain_manifests / "README.md"),
            "role": "domain_manifests_guide",
            "usage": "short explanation of domain and environment contract artifacts",
        },
        {
            "artifact_group": "domain_manifests",
            "path": str(layout.domain_manifests / "environment_registry.csv"),
            "role": "environment_registry",
            "usage": "authoritative E1/E2/E3 boundary and status contract",
        },
        {
            "artifact_group": "domain_manifests",
            "path": str(layout.domain_manifests / "sample_environment_manifest.parquet"),
            "role": "sample_environment_manifest",
            "usage": "sample-to-environment assignment with half-open boundary semantics",
        },
        {
            "artifact_group": "domain_manifests",
            "path": str(layout.domain_manifests / "e1_fold_registry.csv"),
            "role": "e1_fold_registry",
            "usage": "authoritative discovery fold and purge contract for 3h and 8h history",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "claim_registry.yaml"),
            "role": "claim_registry",
            "usage": "preregistered claim, metric, and slice contract for tranche 0",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "comparison_registry.csv"),
            "role": "comparison_registry",
            "usage": "registered ablation pairs and estimands",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "experiment_registry.csv"),
            "role": "experiment_registry",
            "usage": "registered experiment arms and manifest references",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "legacy_to_v2_equivalence_report.csv"),
            "role": "legacy_to_v2_equivalence_report",
            "usage": "migration equivalence between legacy and tranche-0 v2 manifests",
        },
        {
            "artifact_group": "validity_diagnostics",
            "path": str(layout.validity_diagnostics / "README.md"),
            "role": "validity_diagnostics_guide",
            "usage": "short explanation of representation and estimability audits",
        },
        {
            "artifact_group": "validity_diagnostics",
            "path": str(layout.validity_representation / "class_specific_retention.csv"),
            "role": "representation_retention",
            "usage": "class-specific retention from native task cohorts to matched same-Y cohorts",
        },
        {
            "artifact_group": "validity_diagnostics",
            "path": str(layout.validity_representation / "native_vs_matched_distribution.csv"),
            "role": "representation_distribution_shift",
            "usage": "native-versus-matched class distribution distortion by comparison side",
        },
        {
            "artifact_group": "validity_diagnostics",
            "path": str(layout.validity_representation / "representation_validity_report.md"),
            "role": "representation_report",
            "usage": "human-readable representation-validity summary for primary same-Y comparisons",
        },
        {
            "artifact_group": "validity_diagnostics",
            "path": str(layout.validity_evaluation / "estimability_matrix.csv"),
            "role": "estimability_matrix",
            "usage": "normalized trainability, selectability, and estimability states by partition and cohort",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_protocol / "README.md"),
            "role": "primary_protocol_guide",
            "usage": "short explanation of the locked primary protocol artifact tree",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_folds / "fold_manifest.csv"),
            "role": "authoritative_training_protocol",
            "usage": "locked 5-day Fold 01-03 manifest",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_folds / "base_split_assignments.parquet"),
            "role": "authoritative_base_assignments",
            "usage": "record-level base train/validation/test/target_test assignments",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_folds / "view_effective_split_assignments.parquet"),
            "role": "authoritative_effective_assignments",
            "usage": "view-aware eligible/excluded assignments for training",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_folds / "unsupported_class_audit.csv"),
            "role": "class_support_audit",
            "usage": "missing class support by fold partition and task",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_cohorts / "matched_cohort_validation.csv"),
            "role": "cohort_validation",
            "usage": "same-Y alignment validation for primary runner",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "README.md"),
            "role": "primary_runner_guide",
            "usage": "short explanation of the downstream runner manifests",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "runner_contract.json"),
            "role": "runner_contract",
            "usage": "downstream authoritative contract for matched primary cohorts",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "runner_contract_v2.json"),
            "role": "runner_contract_v2",
            "usage": "additive tranche-0 registry and digest contract",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "task_view_registry.csv"),
            "role": "task_view_registry",
            "usage": "explicit mapping between feature views, label tasks, and protocol views",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "task_training_manifest.parquet"),
            "role": "training_manifest",
            "usage": "single runner-facing manifest for task/fold/sample training consumption",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "comparison_training_manifest.parquet"),
            "role": "comparison_training_manifest",
            "usage": "matched-cohort runner manifest keyed by comparison_id and feature view",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "frozen_target_manifest.parquet"),
            "role": "frozen_target_manifest",
            "usage": "single-refit source-to-target runner manifest for final P2 evaluation",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "discovery_training_manifest.parquet"),
            "role": "discovery_training_manifest",
            "usage": "tranche-0 discovery manifest with environment-aware digests",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "temporal_falsification_manifest.parquet"),
            "role": "temporal_falsification_manifest",
            "usage": "tranche-0 E1 to E2 falsification manifest with pairing proofs",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "source_expansion_operational_manifest.parquet"),
            "role": "source_expansion_operational_manifest",
            "usage": "operational E1 vs E1+E2 source-expansion contract on locked E3 evaluation",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "source_expansion_matched_budget_manifest.parquet"),
            "role": "source_expansion_matched_budget_manifest",
            "usage": "matched segment/day budget source-expansion contract with fixed repetitions and seeds",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "deployment_transport_manifest.parquet"),
            "role": "deployment_transport_manifest",
            "usage": "tranche-0 deployment transport contract with support-restricted E3 evaluation",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "task_training_manifest_validation.csv"),
            "role": "training_manifest_validation",
            "usage": "count and uniqueness assertions backing the training manifest",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "comparison_training_manifest_validation.csv"),
            "role": "comparison_training_manifest_validation",
            "usage": "count and uniqueness assertions backing the comparison training manifest",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "frozen_target_manifest_validation.csv"),
            "role": "frozen_target_manifest_validation",
            "usage": "count and readiness assertions backing the final P2 evaluation manifest",
        },
        {
            "artifact_group": "primary_protocol",
            "path": str(layout.primary_runner / "runner_assertion_validation.csv"),
            "role": "runner_assertion_audit",
            "usage": "assertion checks backing the runner contract",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.temporal_diagnostics / "README.md"),
            "role": "temporal_diagnostics_guide",
            "usage": "short explanation of support and coverage diagnostics",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.support_5day / "fold_support_manifest.csv"),
            "role": "support_diagnostic",
            "usage": "all 5-day folds including non-primary stress/support candidates",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.support_7day / "fold_support_manifest.csv"),
            "role": "secondary_support_diagnostic",
            "usage": "7-day comparison folds kept only for diagnostics",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.v2_coverage / "v2_coverage_daily.csv"),
            "role": "v2_coverage_daily",
            "usage": "daily V2 3h vs 8h eligibility and exclusion diagnostics",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.v2_coverage / "v2_coverage_range_summary.csv"),
            "role": "v2_coverage_range_summary",
            "usage": "range-level V2 3h vs 8h coverage loss summary for late P1 and P2",
        },
        {
            "artifact_group": "temporal_diagnostics",
            "path": str(layout.v2_coverage / "v2_coverage_report.md"),
            "role": "v2_coverage_report",
            "usage": "human-readable explanation of V2 8h coverage loss relative to 3h",
        },
        {
            "artifact_group": "transport_diagnostics",
            "path": str(layout.transport_diagnostics / "README.md"),
            "role": "transport_diagnostics_guide",
            "usage": "short explanation of P1-to-P2 drift artifacts",
        },
        {
            "artifact_group": "transport_diagnostics",
            "path": str(layout.transport_feature_shift / "cross_position_feature_shift_raw.csv"),
            "role": "feature_shift_raw",
            "usage": "direct P1-to-P2 feature drift statistics",
        },
        {
            "artifact_group": "transport_diagnostics",
            "path": str(layout.transport_feature_shift / "cross_position_feature_shift_isr.csv"),
            "role": "feature_shift_isr",
            "usage": "standardized feature drift diagnostics",
        },
        {
            "artifact_group": "transport_diagnostics",
            "path": str(layout.transport_label_shift / "cross_position_label_transport.csv"),
            "role": "label_transport_shift",
            "usage": "frozen weak-label prevalence shift report",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_diagnostics / "README.md"),
            "role": "threshold_diagnostics_guide",
            "usage": "short explanation of frozen-threshold and sensitivity artifacts",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_policy / "primary_frozen_initial_source.csv"),
            "role": "frozen_threshold_policy",
            "usage": "authoritative q10 threshold fitted on initial P1 train",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_policy / "threshold_sensitivity_diagnostic.csv"),
            "role": "threshold_fit_diagnostic",
            "usage": "q05/q10/q15/q20 fitted values and fit counts",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_transport / "threshold_sensitivity_transport.csv"),
            "role": "threshold_transport_summary",
            "usage": "summary effect of alternate diagnostic thresholds",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_transport / "threshold_sensitivity_distributions.csv"),
            "role": "threshold_transport_distribution",
            "usage": "distribution-level effect of alternate diagnostic thresholds",
        },
        {
            "artifact_group": "dependency_manifests",
            "path": str(layout.dependency_manifests / "README.md"),
            "role": "dependency_manifests_guide",
            "usage": "short explanation of dependency and proxy-risk manifests",
        },
        {
            "artifact_group": "dependency_manifests",
            "path": str(layout.dependency_manifests / "label_dependency_registry_field_level.csv"),
            "role": "dependency_registry",
            "usage": "auditable direct rule and proxy dependency registry",
        },
        {
            "artifact_group": "dependency_manifests",
            "path": str(layout.dependency_manifests / "proxy_rich_features.csv"),
            "role": "proxy_feature_manifest",
            "usage": "full proxy feature list for reproducibility",
        },
        {
            "artifact_group": "dependency_manifests",
            "path": str(layout.dependency_manifests / "proxy_reduced_features.csv"),
            "role": "proxy_feature_manifest_reduced",
            "usage": "reduced proxy feature list for lean baselines",
        },
    ]
