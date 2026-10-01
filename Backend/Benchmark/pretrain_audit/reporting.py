from __future__ import annotations

import json


def render_audit_report(manifest: dict[str, object]) -> str:
    targets = manifest["alignment"]["target_status"]
    target_rows = [
        f"| `{name}` | {row['known_count']} | {row['missing_count']} | "
        f"{row['distinct_known_values']} | {'yes' if row['fit_estimable_on_full_input'] else 'no'} |"
        for name, row in targets.items()
    ]
    missing_features = manifest["feature_quality"]["all_missing_count"]
    status = manifest["audit_status"]
    support_gate = manifest.get("support_gate")
    support_lines: list[str] = []
    if support_gate is not None:
        support_lines = [
            "",
            "## External support gate",
            "",
            f"- Profile: `{support_gate['profile_id']}`",
            f"- All selected targets pass: {'yes' if support_gate['all_selected_targets_pass'] else 'no'}",
            "| Target | Gate status | Partition results |",
            "|---|---|---|",
        ]
        for target, item in support_gate["targets"].items():
            parts = ", ".join(f"{partition}={'pass' if passed else 'fail'}" for partition, passed in item["partition_status"].items())
            support_lines.append(f"| `{target}` | {item['status']} | {parts} |")
    return "\n".join(
        [
            f"# Pre-train audit: {manifest['run_id']}",
            "",
            f"- Status: **{status}**",
            f"- Samples aligned to protocol: {manifest['alignment']['audit_sample_count']}",
            f"- Selected features: {manifest['selection']['feature_count']}",
            f"- All-missing selected features: {missing_features}",
            f"- Selected groups: `{', '.join(manifest['selection']['selected_groups'])}`",
            f"- Training-label policy: `{manifest.get('training_label_policy', 'complete_case')}`",
            "",
            "## Target support",
            "",
            "| Target | Known | Missing | Distinct values | Estimable on full input |",
            "|---|---:|---:|---:|:---:|",
            *target_rows,
            *support_lines,
            "",
            "The audit artifacts keep feature values, target values, and split metadata in separate files.",
            "",
        ]
    )
