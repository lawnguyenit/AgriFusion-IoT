from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WeakLabelsArtifactLayout:
    root: Path
    run_metadata: Path
    registries: Path
    point: Path
    v2: Path
    v6: Path
    audits: Path
    threshold_diagnostics: Path

    def create(self) -> None:
        for path in (
            self.run_metadata,
            self.registries,
            self.point,
            self.v2,
            self.v6,
            self.audits,
            self.threshold_diagnostics,
        ):
            path.mkdir(parents=True, exist_ok=True)


def build_weak_labels_artifact_layout(root: Path) -> WeakLabelsArtifactLayout:
    return WeakLabelsArtifactLayout(
        root=root,
        run_metadata=root / "run_metadata",
        registries=root / "registries",
        point=root / "point",
        v2=root / "v2",
        v6=root / "v6",
        audits=root / "audits",
        threshold_diagnostics=root / "threshold_diagnostics",
    )


def build_artifact_catalog(layout: WeakLabelsArtifactLayout) -> list[dict[str, str]]:
    return [
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "run_manifest.json"),
            "role": "run_reproducibility",
            "usage": "primary provenance and output-hash manifest",
        },
        {
            "artifact_group": "run_metadata",
            "path": str(layout.run_metadata / "artifact_catalog.csv"),
            "role": "artifact_index",
            "usage": "single-file index of authoritative weak-label outputs",
        },
        {
            "artifact_group": "registries",
            "path": str(layout.registries / "label_registry.yaml"),
            "role": "label_ontology_registry",
            "usage": "task and label ontology definition",
        },
        {
            "artifact_group": "registries",
            "path": str(layout.registries / "label_dependency_registry.csv"),
            "role": "dependency_registry",
            "usage": "direct sources and proxy dependencies by task",
        },
        {
            "artifact_group": "point",
            "path": str(layout.point / "point_evidence_flags.parquet"),
            "role": "point_evidence",
            "usage": "point-level evidence flags separate from train labels",
        },
        {
            "artifact_group": "point",
            "path": str(layout.point / "point_labels_detailed.parquet"),
            "role": "point_detailed_labels",
            "usage": "full point labeling states including exclusions",
        },
        {
            "artifact_group": "point",
            "path": str(layout.point / "point_labels_train.parquet"),
            "role": "point_train_labels",
            "usage": "authoritative V0/V1 train targets",
        },
        {
            "artifact_group": "point",
            "path": str(layout.point / "technical_labels_audit.parquet"),
            "role": "technical_audit",
            "usage": "technical-invalid audit states kept separate from environmental classes",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_same_y_labels.parquet"),
            "role": "v2_same_y_labels",
            "usage": "same-Y copies of V0/V1 point targets",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_temporal_evidence_3h.parquet"),
            "role": "v2_temporal_evidence",
            "usage": "3h causal temporal evidence anchored at current row",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_temporal_evidence_8h.parquet"),
            "role": "v2_temporal_evidence",
            "usage": "8h causal temporal evidence anchored at current row",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_temporal_labels_3h.parquet"),
            "role": "v2_temporal_labels",
            "usage": "3h temporal train/exclusion labels",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_temporal_labels_8h.parquet"),
            "role": "v2_temporal_labels",
            "usage": "8h temporal train/exclusion labels",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "matched_cohort_manifest.parquet"),
            "role": "same_y_matched_manifest",
            "usage": "matched record manifest for same-Y comparisons",
        },
        {
            "artifact_group": "v2",
            "path": str(layout.v2 / "v2_label_agreement_3h_8h.csv"),
            "role": "horizon_agreement_audit",
            "usage": "agreement summary between 3h and 8h temporal outputs",
        },
        {
            "artifact_group": "v6",
            "path": str(layout.v6 / "v6_event_labels.parquet"),
            "role": "v6_event_labels",
            "usage": "authoritative V6-E event labels",
        },
        {
            "artifact_group": "v6",
            "path": str(layout.v6 / "v6_b8_block_composition.parquet"),
            "role": "v6_block_composition",
            "usage": "event-overlap composition of fixed local-time blocks",
        },
        {
            "artifact_group": "v6",
            "path": str(layout.v6 / "v6_b8_block_labels.parquet"),
            "role": "v6_block_labels",
            "usage": "authoritative V6-B8 block labels",
        },
        {
            "artifact_group": "v6",
            "path": str(layout.v6 / "boundary_event_audit.parquet"),
            "role": "v6_boundary_audit",
            "usage": "boundary-crossing event exclusions",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "label_distribution.csv"),
            "role": "distribution_audit",
            "usage": "label counts by task and partition",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "label_overlap_matrix.csv"),
            "role": "overlap_audit",
            "usage": "record-level overlap matrix across record tasks",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "excluded_samples_audit.csv"),
            "role": "exclusion_audit",
            "usage": "all excluded or abstained samples across tasks",
        },
        {
            "artifact_group": "audits",
            "path": str(layout.audits / "label_examples.csv"),
            "role": "example_audit",
            "usage": "small examples per task and label",
        },
        {
            "artifact_group": "threshold_diagnostics",
            "path": str(layout.threshold_diagnostics / "threshold_sensitivity.csv"),
            "role": "threshold_sensitivity",
            "usage": "diagnostic threshold quantiles and fit support",
        },
    ]
