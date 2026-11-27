from __future__ import annotations

from pathlib import Path

import pandas as pd


def summarize_continuity_sensitivity(
    runs: list[tuple[float, Path]],
    *,
    target_id: str,
    tail_share: float,
    tau_minutes: int,
) -> pd.DataFrame:
    """Combine B2-A and B2-E evidence for equivalent-label continuity runs."""
    rows: list[dict[str, object]] = []
    for g_max, support_dir in runs:
        gate = pd.read_csv(support_dir / "candidate_support_gate.csv").convert_dtypes()
        gate_summary = pd.read_csv(support_dir / "candidate_gate_summary.csv").convert_dtypes()
        entity = pd.read_csv(support_dir / "candidate_entity_support.csv").convert_dtypes()
        entity_summary = pd.read_csv(support_dir / "candidate_entity_estimability.csv").convert_dtypes()
        selector = (
            gate["target_id"].astype("string").eq(target_id)
            & pd.to_numeric(gate["tail_share"], errors="coerce").eq(tail_share)
            & pd.to_numeric(gate["tau_minutes"], errors="coerce").eq(tau_minutes)
            & gate["threshold_scope"].astype("string").eq("per_entity")
        )
        selected_gate = gate.loc[selector]
        if selected_gate.empty or selected_gate["partition"].nunique() != 3:
            raise ValueError(f"g_max={g_max} support run does not contain the expected primary B2-A candidate.")
        gate_selector = (
            gate_summary["target_id"].astype("string").eq(target_id)
            & pd.to_numeric(gate_summary["tail_share"], errors="coerce").eq(tail_share)
            & pd.to_numeric(gate_summary["tau_minutes"], errors="coerce").eq(tau_minutes)
            & gate_summary["threshold_scope"].astype("string").eq("per_entity")
        )
        candidate_status = gate_summary.loc[gate_selector]
        if len(candidate_status) != 1:
            raise ValueError(f"g_max={g_max} support summary does not resolve exactly one primary candidate.")
        all_pass = bool(candidate_status.iloc[0]["all_partitions_pass"])
        for item in selected_gate.to_dict(orient="records"):
            rows.append({
                "g_max_cadence_fraction": g_max,
                "support_layer": "B2-A",
                "entity_id": "__AGGREGATE__",
                "target_id": item["target_id"],
                "q_id": item["q_id"],
                "threshold_scope": item["threshold_scope"],
                "tail_share": item["tail_share"],
                "tau_minutes": item["tau_minutes"],
                "partition": item["partition"],
                "row_count": item["row_count"],
                "known_label_count": item["known_label_count"],
                "unknown_label_count": item["unknown_label_count"],
                "positive_count": item["positive_class_count"],
                "negative_count": item["negative_class_count"],
                "persistent_event_onsets": item["persistent_event_count"],
                "episode_cluster_count": item["episode_cluster_count"],
                "discrimination_estimable": pd.NA,
                "support_adequate": bool(item["support_gate_pass"]),
                "discrimination_status": pd.NA,
                "support_adequacy_status": "PASS" if bool(item["support_gate_pass"]) else "FAIL",
                "partition_discrimination_status": pd.NA,
                "partition_support_adequacy_status": pd.NA,
                "candidate_all_partitions_pass": all_pass,
                "support_audit_dir": str(support_dir.resolve()),
            })
        entity_selector = (
            entity["target_id"].astype("string").eq(target_id)
            & pd.to_numeric(entity["tail_share"], errors="coerce").eq(tail_share)
            & pd.to_numeric(entity["tau_minutes"], errors="coerce").eq(tau_minutes)
            & entity["threshold_scope"].astype("string").eq("per_entity")
        )
        selected_entity = entity.loc[entity_selector]
        selected_summary = entity_summary.loc[
            entity_summary["target_id"].astype("string").eq(target_id)
            & pd.to_numeric(entity_summary["tail_share"], errors="coerce").eq(tail_share)
            & pd.to_numeric(entity_summary["tau_minutes"], errors="coerce").eq(tau_minutes)
            & entity_summary["threshold_scope"].astype("string").eq("per_entity")
        ]
        for item in selected_entity.to_dict(orient="records"):
            summary = selected_summary.loc[selected_summary["partition"].astype("string").eq(str(item["partition"]))]
            summary_row = summary.iloc[0] if not summary.empty else {}
            rows.append({
                "g_max_cadence_fraction": g_max,
                "support_layer": "B2-E",
                "entity_id": item["entity_id"],
                "target_id": item["target_id"],
                "q_id": item["q_id"],
                "threshold_scope": item["threshold_scope"],
                "tail_share": item["tail_share"],
                "tau_minutes": item["tau_minutes"],
                "partition": item["partition"],
                "row_count": item["row_count"],
                "known_label_count": item["known_label_count"],
                "unknown_label_count": item["unknown_label_count"],
                "positive_count": item["positive_count"],
                "negative_count": item["negative_count"],
                "persistent_event_onsets": item["persistent_event_onsets"],
                "episode_cluster_count": item["episode_cluster_count"],
                "discrimination_estimable": item["within_entity_discrimination_estimable"],
                "support_adequate": item["within_entity_support_adequate"],
                "discrimination_status": "PASS" if bool(item["within_entity_discrimination_estimable"]) else "FAIL",
                "support_adequacy_status": "PASS" if bool(item["within_entity_support_adequate"]) else "FAIL",
                "partition_discrimination_status": summary_row.get("entity_discrimination_status", pd.NA),
                "partition_support_adequacy_status": summary_row.get("entity_support_adequacy_status", pd.NA),
                "candidate_all_partitions_pass": all_pass,
                "support_audit_dir": str(support_dir.resolve()),
            })
    return pd.DataFrame(rows).convert_dtypes().sort_values(
        ["g_max_cadence_fraction", "support_layer", "partition", "entity_id"], kind="stable"
    ).reset_index(drop=True)
