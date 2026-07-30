from __future__ import annotations

from Backend.Benchmark.evaluation_protocols.pipeline.layout import EvaluationArtifactLayout


def build_root_artifact_guide() -> str:
    return "\n".join(
        [
            "# Evaluation Protocols Artifact Guide",
            "",
            "## Input",
            "- one frozen Layer1 canonical telemetry history",
            "- one linked `dataset_views` run as feature authority",
            "- one linked `weak_labels` run as label authority",
            "- protocol config for fold, threshold, and transport rules",
            "",
            "## This Layer Does",
            "- decide which rows belong to source development, exploratory falsification, and target transport",
            "- define the train/eval boundaries that downstream runners must obey",
            "- convert feature authority plus label authority into runner-facing manifests and scientific registries",
            "",
            "## Output",
            "- `run_metadata/`: start here for provenance and gate status",
            "- `domain_manifests/`: boundary contracts for domains, environments, and E1 folds",
            "- `primary_protocol/`: manifests that downstream training actually consumes",
            "- `temporal_diagnostics/`: support and coverage diagnostics, not the main train contract",
            "- `transport_diagnostics/`: raw and standardized P1-to-P2 drift checks",
            "- `threshold_diagnostics/`: frozen threshold policy and sensitivity outputs",
            "- `validity_diagnostics/`: representation and estimability audits above the raw manifests",
            "- `dependency_manifests/`: supporting scientific audits",
            "",
            "## Read Order",
            "1. `run_metadata/artifact_catalog.csv`",
            "2. `run_metadata/protocol_validation_report.json`",
            "3. `domain_manifests/environment_registry.csv`",
            "4. `domain_manifests/e1_fold_registry.csv`",
            "5. `primary_protocol/runner/task_view_registry.csv`",
            "6. `primary_protocol/runner/task_training_manifest.parquet`",
            "7. `primary_protocol/runner/comparison_training_manifest.parquet`",
            "8. `primary_protocol/runner/runner_contract_v2.json`",
        ]
    )


def build_run_metadata_readme() -> str:
    return "\n".join(
        [
            "# Run Metadata",
            "",
            "## Input",
            "- the completed protocol build and all artifact paths it produced",
            "",
            "## This Folder Does",
            "- record what this run used, what it produced, and whether the build passed contract gates",
            "",
            "## Output",
            "- `artifact_catalog.csv`: map of authoritative outputs",
            "- `protocol_validation_report.json`: gate summary and blockers",
            "- `run_manifest.json`: provenance and linked input runs",
            "- `claim_registry.yaml`: preregistered claim contract",
            "- `comparison_registry.csv`: registered scientific comparisons",
            "- `experiment_registry.csv`: experiment arms and manifest bindings",
            "- `legacy_to_v2_equivalence_report.csv`: migration comparison against legacy manifests",
        ]
    )


def build_domain_manifests_readme() -> str:
    return "\n".join(
        [
            "# Domain Manifests",
            "",
            "## Input",
            "- canonical timestamps, segment ownership, and deployment mapping rules",
            "",
            "## This Folder Does",
            "- define where P1 ends, where P2 begins, and how E1/E2/E3 and E1 folds are assigned",
            "",
            "## Output",
            "- `deployment_domains.csv`: raw P1/P2 domain ownership by row",
            "- `environment_registry.csv`: authoritative E1/E2/E3 boundary contract",
            "- `sample_environment_manifest.parquet`: sample-to-environment assignment",
            "- `e1_fold_registry.csv`: authoritative discovery fold and purge contract",
        ]
    )


def build_primary_protocol_readme() -> str:
    return "\n".join(
        [
            "# Primary Protocol",
            "",
            "## Input",
            "- domain assignments",
            "- linked feature views",
            "- linked weak labels",
            "- matched-cohort and fold rules",
            "",
            "## This Folder Does",
            "- assemble the locked benchmark protocol that downstream training is supposed to follow",
            "",
            "## Output",
            "- `folds/`: base and view-aware split assignments",
            "- `cohorts/`: matched same-Y cohort manifests",
            "- `lineage/`: support files explaining fold and assignment exclusions",
            "- `runner/`: actual downstream training manifests and contracts",
        ]
    )


def build_primary_runner_readme() -> str:
    return "\n".join(
        [
            "# Primary Runner",
            "",
            "## Input",
            "- locked primary folds and matched cohorts",
            "- resolved feature artifacts from `dataset_views`",
            "- resolved weak-label artifacts from `weak_labels`",
            "",
            "## This Folder Does",
            "- produce the machine-readable manifests that `model_suite` trains from",
            "",
            "## Output",
            "- `task_view_registry.csv`: map feature view to label task and protocol view",
            "- `task_training_manifest.parquet`: row-level task train/eval manifest",
            "- `comparison_training_manifest.parquet`: paired same-Y manifest",
            "- `frozen_target_manifest.parquet`: final source-to-E3 evaluation manifest",
            "- `runner_contract.json`: legacy runner contract",
            "- `runner_contract_v2.json`: tranche-0 contract with registries and digests",
            "- `*_validation.csv`: assertions backing each manifest",
            "- `discovery_training_manifest.parquet`: E1 discovery contract",
            "- `temporal_falsification_manifest.parquet`: E1 to E2 exploratory falsification contract",
            "- `source_expansion_*`: source-expansion manifests",
            "- `deployment_transport_manifest.parquet`: support-restricted E3 transport contract",
        ]
    )


def build_temporal_diagnostics_readme() -> str:
    return "\n".join(
        [
            "# Temporal Diagnostics",
            "",
            "## Input",
            "- P1 source rows, fold specs, and V2 evidence windows",
            "",
            "## This Folder Does",
            "- explain temporal support, stress eligibility, and why 3h and 8h windows keep or lose anchors",
            "",
            "## Output",
            "- `support_5day/`: diagnostics for all 5-day folds",
            "- `secondary_7day/`: diagnostics for secondary 7-day folds",
            "- `v2_coverage/`: 3h vs 8h coverage-loss audits",
        ]
    )


def build_transport_diagnostics_readme() -> str:
    return "\n".join(
        [
            "# Transport Diagnostics",
            "",
            "## Input",
            "- P1 and P2 canonical rows plus frozen source threshold policy",
            "",
            "## This Folder Does",
            "- quantify what changes when the benchmark is transported from P1 to P2",
            "",
            "## Output",
            "- `feature_shift/`: raw and standardized feature drift tables",
            "- `label_shift/`: frozen weak-label prevalence shift table",
        ]
    )


def build_threshold_diagnostics_readme() -> str:
    return "\n".join(
        [
            "# Threshold Diagnostics",
            "",
            "## Input",
            "- initial source threshold fit context and alternate quantile settings",
            "",
            "## This Folder Does",
            "- publish the frozen primary threshold and show how alternate threshold choices would move downstream diagnostics",
            "",
            "## Output",
            "- `policy/`: frozen q10 threshold and fitting summary",
            "- `transport/`: threshold sensitivity summaries and distributions",
        ]
    )


def build_validity_diagnostics_readme() -> str:
    return "\n".join(
        [
            "# Validity Diagnostics",
            "",
            "## Input",
            "- runner manifests and matched cohorts from the locked primary protocol",
            "",
            "## This Folder Does",
            "- check whether the chosen representation and matched cohorts still preserve enough support to interpret results safely",
            "",
            "## Output",
            "- `representation/`: class retention and native-vs-matched distortion",
            "- `evaluation/estimability_matrix.csv`: normalized estimability states by partition and cohort",
        ]
    )


def build_dependency_manifests_readme() -> str:
    return "\n".join(
        [
            "# Dependency Manifests",
            "",
            "## Input",
            "- registered knowledge about direct rule sources and proxy-risk features",
            "",
            "## This Folder Does",
            "- expose which features are scientifically risky, directly rule-derived, or relatively safe for lean baselines",
            "",
            "## Output",
            "- `label_dependency_registry_field_level.csv`: field-level dependency registry",
            "- `proxy_rich_features.csv`: broad proxy-risk feature list",
            "- `proxy_reduced_features.csv`: reduced feature list after removing direct rule sources",
        ]
    )
def write_artifact_guides(layout: EvaluationArtifactLayout) -> None:
    (layout.root / "ARTIFACT_GUIDE.md").write_text(build_root_artifact_guide() + "\n", encoding="utf-8")
    (layout.run_metadata / "README.md").write_text(build_run_metadata_readme() + "\n", encoding="utf-8")
    (layout.domain_manifests / "README.md").write_text(build_domain_manifests_readme() + "\n", encoding="utf-8")
    (layout.primary_protocol / "README.md").write_text(build_primary_protocol_readme() + "\n", encoding="utf-8")
    (layout.primary_runner / "README.md").write_text(build_primary_runner_readme() + "\n", encoding="utf-8")
    (layout.temporal_diagnostics / "README.md").write_text(build_temporal_diagnostics_readme() + "\n", encoding="utf-8")
    (layout.transport_diagnostics / "README.md").write_text(build_transport_diagnostics_readme() + "\n", encoding="utf-8")
    (layout.threshold_diagnostics / "README.md").write_text(build_threshold_diagnostics_readme() + "\n", encoding="utf-8")
    (layout.validity_diagnostics / "README.md").write_text(build_validity_diagnostics_readme() + "\n", encoding="utf-8")
    (layout.dependency_manifests / "README.md").write_text(build_dependency_manifests_readme() + "\n", encoding="utf-8")
