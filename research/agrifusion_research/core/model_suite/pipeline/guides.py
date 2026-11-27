from __future__ import annotations

from pathlib import Path


def build_root_artifact_guide() -> str:
    return "\n".join(
        [
            "# Model Suite Artifact Guide",
            "",
            "## Input",
            "- one linked `evaluation_protocols` run as protocol authority",
            "- one selected training profile",
            "- one selected model set plus artifact-policy config",
            "",
            "## This Layer Does",
            "- load the locked train/eval manifests from the protocol layer",
            "- train the requested model families on allowed rows only",
            "- evaluate them on registered partitions and slices",
            "- emit per-job predictions, metrics, validation, and model bundles",
            "",
            "## Output",
            "- `run_manifest.json`: provenance for this whole model run",
            "- `artifact_catalog.csv`: index of the authoritative outputs",
            "- `profiles/` or `smoke_protocol/`: summary tables plus nested job artifacts",
            "",
            "## Read Order",
            "1. `artifact_catalog.csv`",
            "2. `run_manifest.json`",
            "3. `profiles/<profile>/README.md` or `smoke_protocol/README.md`",
            "4. `training_summary.csv` or `smoke_model_summary.csv`",
            "5. `training_validation.csv` or `smoke_model_validation.csv`",
            "6. one job folder's `metrics.json`, `run_validation.json`, and `run_metadata.json`",
        ]
    )


def build_profiles_root_readme() -> str:
    return "\n".join(
        [
            "# Profiles",
            "",
            "## Input",
            "- completed model jobs grouped under one named training profile",
            "",
            "## This Folder Does",
            "- separate one benchmark profile from another so each profile has its own summary tables and nested job outputs",
            "",
            "## Output",
            "- one folder per profile name",
            "- inside each profile: summary tables, pooled metrics, report, and `jobs/`",
        ]
    )


def build_profile_readme(profile_name: str) -> str:
    return "\n".join(
        [
            f"# Profile `{profile_name}`",
            "",
            "## Input",
            "- one protocol runner contract",
            "- one registered profile stage specification",
            "- one selected model set",
            "",
            "## This Folder Does",
            "- collect all jobs that belong to this profile and summarize them at the profile level",
            "",
            "## Output",
            "- `training_summary.csv`: one row per trained or skipped job",
            "- `training_validation.csv`: partition and cohort gate checks",
            "- `per_sample_predictions.csv`: held-out prediction rows pooled across jobs",
            "- `pooled_metrics.csv`: aggregated metric view across jobs",
            "- `model_comparison_table.csv`: compact side-by-side comparison",
            "- `run_report.md`: short human-readable profile summary",
            "- `jobs/`: per-stage, per-model, per-view, per-fold job artifacts",
        ]
    )


def build_smoke_protocol_readme(profile_name: str) -> str:
    return "\n".join(
        [
            f"# Smoke Protocol `{profile_name}`",
            "",
            "## Input",
            "- one protocol runner contract",
            "- one smoke profile specification",
            "- a lightweight model subset",
            "",
            "## This Folder Does",
            "- run the conservative smoke benchmark and keep both summary outputs and nested job outputs in one place",
            "",
            "## Output",
            "- `smoke_model_summary.csv`: one row per smoke job",
            "- `smoke_model_validation.csv`: gate checks for smoke jobs",
            "- `per_sample_predictions.csv`: pooled smoke predictions",
            "- `pooled_metrics.csv`: pooled smoke metrics",
            "- `model_comparison_table.csv`: compact smoke comparison table",
            "- `smoke_report.md`: short human-readable smoke summary",
            "- stage/model/view/fold folders with per-job artifacts",
        ]
    )


def build_jobs_readme() -> str:
    return "\n".join(
        [
            "# Jobs",
            "",
            "## Input",
            "- one profile-scoped set of stage/model/view/fold executions",
            "",
            "## This Folder Does",
            "- store the real per-job evidence that downstream synthesis will consume",
            "",
            "## Output",
            "- nested stage/model/comparison-or-task/view/fold directories",
            "- inside each job folder: model bundle, predictions, metrics, validation, and exact-rule-control outputs",
            "",
            "## Main Files Inside One Job Folder",
            "- `metrics.json`",
            "- `predictions.parquet`",
            "- `per_class_metrics.csv`",
            "- `slice_metrics.csv`",
            "- `confusion_matrix.csv`",
            "- `feature_effects.csv`",
            "- `run_validation.json`",
            "- `run_metadata.json`",
            "- `rule_control_summary.json`",
            "- `disagreement_samples.parquet`",
        ]
    )


def write_run_guides(*, output_dir: Path, profile_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    root_guide_path = output_dir / "ARTIFACT_GUIDE.md"
    root_guide_path.write_text(build_root_artifact_guide() + "\n", encoding="utf-8")
    rows.append(
        {
            "artifact_group": "run_metadata",
            "path": str(root_guide_path),
            "role": "artifact_guide",
            "usage": "reader-first overview of what this model run takes in, does, and writes out",
        }
    )
    if profile_name.startswith("smoke_"):
        smoke_root = output_dir / "smoke_protocol"
        smoke_root.mkdir(parents=True, exist_ok=True)
        smoke_readme_path = smoke_root / "README.md"
        smoke_readme_path.write_text(build_smoke_protocol_readme(profile_name) + "\n", encoding="utf-8")
        rows.append(
            {
                "artifact_group": "profile_run",
                "path": str(smoke_readme_path),
                "role": "smoke_protocol_guide",
                "usage": f"short explanation of the smoke artifact group for profile {profile_name}",
            }
        )
        return rows

    profiles_root = output_dir / "profiles"
    profiles_root.mkdir(parents=True, exist_ok=True)
    profiles_readme_path = profiles_root / "README.md"
    profiles_readme_path.write_text(build_profiles_root_readme() + "\n", encoding="utf-8")
    rows.append(
        {
            "artifact_group": "profile_run",
            "path": str(profiles_readme_path),
            "role": "profile_group_guide",
            "usage": "short explanation of how profile-scoped model runs are grouped",
        }
    )
    profile_root = profiles_root / profile_name
    profile_root.mkdir(parents=True, exist_ok=True)
    profile_readme_path = profile_root / "README.md"
    profile_readme_path.write_text(build_profile_readme(profile_name) + "\n", encoding="utf-8")
    rows.append(
        {
            "artifact_group": "profile_run",
            "path": str(profile_readme_path),
            "role": "profile_run_guide",
            "usage": f"short explanation of profile {profile_name} summary outputs",
        }
    )
    jobs_root = profile_root / "jobs"
    jobs_root.mkdir(parents=True, exist_ok=True)
    jobs_readme_path = jobs_root / "README.md"
    jobs_readme_path.write_text(build_jobs_readme() + "\n", encoding="utf-8")
    rows.append(
        {
            "artifact_group": "profile_run",
            "path": str(jobs_readme_path),
            "role": "job_group_guide",
            "usage": f"short explanation of nested per-job artifacts for profile {profile_name}",
        }
    )
    return rows
