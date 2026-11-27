from __future__ import annotations

from pathlib import Path


DATASET_ARTIFACT_ALIASES: dict[str, tuple[str, ...]] = {
    "benchmark_input_aligned.csv": ("flb_input_aligned.csv",),
    "benchmark_input_labeled.csv": ("flb_input_with_events.csv",),
    "single_window_exp1.csv": ("flb_l2_exp1.csv",),
    "single_window_exp2.csv": ("flb_l2_exp2.csv",),
    "single_window_exp3.csv": ("flb_l2_exp3.csv",),
    "single_window_exp4.csv": ("flb_l2_exp4.csv",),
    "single_window_exp5.csv": ("flb_l2_exp5.csv",),
    "single_window_exp6.csv": ("flb_l2_exp6.csv",),
    "multi_window_combo1.csv": ("flb_l3_combo1.csv",),
    "multi_window_combo2.csv": ("flb_l3_combo2.csv",),
    "multi_window_combo3.csv": ("flb_l3_combo3.csv",),
    "multi_window_combo4.csv": ("flb_l3_combo4.csv",),
}


def resolve_dataset_artifact(dataset_root: Path, canonical_name: str) -> Path:
    root = dataset_root.resolve()
    candidate_names = (canonical_name, *DATASET_ARTIFACT_ALIASES.get(canonical_name, ()))
    for candidate_name in candidate_names:
        candidate_path = (root / candidate_name).resolve()
        if candidate_path.exists():
            return candidate_path
    return (root / canonical_name).resolve()


def resolve_dataset_artifact_path(path: Path, dataset_root: Path) -> Path:
    resolved_path = path.resolve()
    root = dataset_root.resolve()
    if resolved_path.parent != root:
        return resolved_path
    return resolve_dataset_artifact(root, resolved_path.name)
