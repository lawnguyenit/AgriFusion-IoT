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
    return "\n".join(
        [
            f"# Pre-train audit: {manifest['run_id']}",
            "",
            f"- Status: **{status}**",
            f"- Samples aligned to protocol: {manifest['alignment']['audit_sample_count']}",
            f"- Selected features: {manifest['selection']['feature_count']}",
            f"- All-missing selected features: {missing_features}",
            f"- Selected groups: `{', '.join(manifest['selection']['selected_groups'])}`",
            "",
            "## Target support",
            "",
            "| Target | Known | Missing | Distinct values | Estimable on full input |",
            "|---|---:|---:|---:|:---:|",
            *target_rows,
            "",
            "The audit artifacts keep feature values, target values, and split metadata in separate files.",
            "",
        ]
    )
