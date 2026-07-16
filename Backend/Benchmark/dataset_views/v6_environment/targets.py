from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    V6_EC_SHIFT_DELTA_Q,
    V6_LOW_MOISTURE_ONSET_MIN_STEPS,
    V6_RAPID_WETTING_DELTA_PP,
    V6_THERMAL_VPD_THRESHOLD_KPA,
)


@dataclass(frozen=True)
class ThresholdBucket:
    low_moisture_q10: float
    low_moisture_q15: float
    ec_shift_abs_delta_q95: float | None


def apply_environment_targets(
    resampled_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    working = resampled_df.copy()
    working["candidate_event_type"] = pd.Series(["normal"] * len(working), index=working.index, dtype="string")
    working["candidate_priority_reason"] = pd.Series(["normal"] * len(working), index=working.index, dtype="string")
    working["original_event_id"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="string")
    working["original_event_start_time"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="string")
    working["original_event_confirmation_time"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="string")
    working["original_event_end_time"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="string")
    working["detailed_event_type"] = pd.Series(["normal"] * len(working), index=working.index, dtype="string")
    working["final_train_label"] = pd.Series(["normal"] * len(working), index=working.index, dtype="string")
    working["online_stage"] = pd.Series(["none"] * len(working), index=working.index, dtype="string")
    working["original_event_step_index"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="Int64")
    working["original_event_run_length"] = pd.Series([pd.NA] * len(working), index=working.index, dtype="Int64")
    working["target_loss_mask"] = working["sequence.observed_mask"].fillna(False).astype("boolean")
    thresholds_manifest: dict[str, object] = {
        "version": "2026-07-15.v6-sequence-thresholds.v1",
        "segments": {},
    }

    for segment_id, group in working.groupby("record.segment_id", sort=False, dropna=False):
        bucket = _fit_threshold_bucket(group)
        thresholds_manifest["segments"][str(segment_id)] = {
            "low_moisture_q10": bucket.low_moisture_q10,
            "low_moisture_q15": bucket.low_moisture_q15,
            "ec_shift_abs_delta_q95": bucket.ec_shift_abs_delta_q95,
            "thermal_vpd_threshold_kpa": V6_THERMAL_VPD_THRESHOLD_KPA,
            "rapid_wetting_delta_pp": V6_RAPID_WETTING_DELTA_PP,
        }
        segment_mask = working["record.segment_id"].astype("string") == str(segment_id)
        working.loc[segment_mask, ["candidate_event_type", "candidate_priority_reason"]] = _assign_pointwise_candidates(
            working.loc[segment_mask].copy(),
            bucket=bucket,
        ).to_numpy()

    _assign_original_event_ids(working)
    _validate_original_event_assignments(working)
    return working, thresholds_manifest


def _fit_threshold_bucket(group: pd.DataFrame) -> ThresholdBucket:
    observed = group.loc[group["sequence.observed_mask"].fillna(False)].copy()
    moisture = pd.to_numeric(observed["npk.soil_moisture_pct"], errors="coerce").dropna()
    if moisture.empty:
        raise ValueError("V6 could not fit low-moisture thresholds because no observed moisture values were available.")
    ec_values = pd.to_numeric(observed["npk.ec"], errors="coerce").dropna()
    ec_shift_q95 = None
    if len(ec_values) >= 2:
        ec_shift_q95 = float(ec_values.diff().abs().dropna().quantile(V6_EC_SHIFT_DELTA_Q))
    return ThresholdBucket(
        low_moisture_q10=float(moisture.quantile(0.10)),
        low_moisture_q15=float(moisture.quantile(0.15)),
        ec_shift_abs_delta_q95=ec_shift_q95,
    )


def _assign_pointwise_candidates(
    group: pd.DataFrame,
    *,
    bucket: ThresholdBucket,
) -> pd.DataFrame:
    ordered = group.sort_values(["sequence.timestamp_grid", "sequence.grid_index"], kind="stable").reset_index()
    candidate_type: list[str] = []
    priority_reason: list[str] = []
    previous_moisture: float | None = None
    previous_ec: float | None = None
    for _, row in ordered.iterrows():
        moisture = pd.to_numeric(pd.Series([row["npk.soil_moisture_pct"]]), errors="coerce").iloc[0]
        ec_value = pd.to_numeric(pd.Series([row["npk.ec"]]), errors="coerce").iloc[0]
        vpd = pd.to_numeric(pd.Series([row["derived.vpd_kpa"]]), errors="coerce").iloc[0]
        if bool(row["sequence.missing_mask"]):
            candidate_type.append("normal")
            priority_reason.append("missing_slot")
            previous_moisture = None if pd.isna(moisture) else float(moisture)
            previous_ec = None if pd.isna(ec_value) else float(ec_value)
            continue

        assigned = "normal"
        reason = "normal"
        if pd.notna(moisture) and float(moisture) <= bucket.low_moisture_q10:
            assigned = "persistent_low_relative_moisture_event"
            reason = "low_moisture_q10"
        elif previous_moisture is not None and pd.notna(moisture) and float(moisture) - previous_moisture >= V6_RAPID_WETTING_DELTA_PP:
            assigned = "rapid_wetting_event_candidate"
            reason = "rapid_wetting_delta"
        elif pd.notna(vpd) and float(vpd) >= V6_THERMAL_VPD_THRESHOLD_KPA:
            assigned = "thermal_dry_air_event_candidate"
            reason = "thermal_vpd"
        elif (
            bucket.ec_shift_abs_delta_q95 is not None
            and bucket.ec_shift_abs_delta_q95 > 0
            and previous_ec is not None
            and pd.notna(ec_value)
            and abs(float(ec_value) - previous_ec) >= bucket.ec_shift_abs_delta_q95
        ):
            assigned = "ec_shift_event_candidate"
            reason = "ec_shift_q95"

        candidate_type.append(assigned)
        priority_reason.append(reason)
        previous_moisture = None if pd.isna(moisture) else float(moisture)
        previous_ec = None if pd.isna(ec_value) else float(ec_value)

    return pd.DataFrame(
        {
            "candidate_event_type": pd.Series(candidate_type, index=ordered["index"].tolist(), dtype="string"),
            "candidate_priority_reason": pd.Series(priority_reason, index=ordered["index"].tolist(), dtype="string"),
        },
    ).sort_index(kind="stable")


def _assign_original_event_ids(working: pd.DataFrame) -> None:
    event_counter = 0
    for _, group in working.groupby("continuity_segment_id", sort=False, dropna=False):
        ordered_indices = (
            group.sort_values(["sequence.timestamp_grid", "sequence.grid_index"], kind="stable").index.tolist()
        )
        active_type = "normal"
        run_indices: list[int] = []
        for index in ordered_indices:
            candidate_type = str(working.loc[index, "candidate_event_type"])
            if candidate_type == "normal":
                if active_type != "normal" and run_indices:
                    event_counter = _finalize_original_run(
                        working,
                        run_indices=run_indices,
                        candidate_type=active_type,
                        event_counter=event_counter,
                    )
                active_type = "normal"
                run_indices = []
                continue
            if candidate_type != active_type and run_indices:
                event_counter = _finalize_original_run(
                    working,
                    run_indices=run_indices,
                    candidate_type=active_type,
                    event_counter=event_counter,
                )
                run_indices = []
            active_type = candidate_type
            run_indices.append(index)
        if active_type != "normal" and run_indices:
            event_counter = _finalize_original_run(
                working,
                run_indices=run_indices,
                candidate_type=active_type,
                event_counter=event_counter,
            )


def _finalize_original_run(
    working: pd.DataFrame,
    *,
    run_indices: list[int],
    candidate_type: str,
    event_counter: int,
) -> int:
    event_counter += 1
    event_id = f"orig_evt_{event_counter:05d}"
    run_length = len(run_indices)
    start_time = str(working.loc[run_indices[0], "sequence.timestamp_grid_iso"])
    end_time = str(working.loc[run_indices[-1], "sequence.timestamp_grid_iso"])
    confirmation_time = str(working.loc[run_indices[2], "sequence.timestamp_grid_iso"]) if run_length >= 3 else pd.NA
    if run_length == 1:
        detailed_event_type = "isolated_unknown_anomaly"
        final_train_label = "unknown_environment_event"
    elif run_length == 2:
        detailed_event_type = "attention_unknown_anomaly"
        final_train_label = "unknown_environment_event"
    else:
        detailed_event_type = candidate_type
        final_train_label = (
            "persistent_low_relative_moisture_event"
            if candidate_type == "persistent_low_relative_moisture_event"
            else "unknown_environment_event"
        )
    working.loc[run_indices, "original_event_id"] = event_id
    working.loc[run_indices, "original_event_start_time"] = start_time
    working.loc[run_indices, "original_event_confirmation_time"] = confirmation_time
    working.loc[run_indices, "original_event_end_time"] = end_time
    working.loc[run_indices, "detailed_event_type"] = detailed_event_type
    working.loc[run_indices, "final_train_label"] = final_train_label
    working.loc[run_indices, "original_event_run_length"] = run_length
    for step_index, row_index in enumerate(run_indices):
        working.loc[row_index, "original_event_step_index"] = step_index
        working.loc[row_index, "online_stage"] = "isolated" if step_index == 0 else "attention" if step_index == 1 else "confirmed"
    if candidate_type == "persistent_low_relative_moisture_event" and run_length < V6_LOW_MOISTURE_ONSET_MIN_STEPS:
        # A short low-moisture candidate is preserved for audit lineage but remains train-mapped to unknown.
        working.loc[run_indices, "final_train_label"] = "unknown_environment_event"
        working.loc[run_indices, "detailed_event_type"] = "attention_unknown_anomaly" if run_length == 2 else "isolated_unknown_anomaly"
    return event_counter


def _validate_original_event_assignments(working: pd.DataFrame) -> None:
    event_rows = working.loc[working["original_event_id"].notna()].copy()
    if event_rows.empty:
        return

    problems: list[str] = []
    for original_event_id, group in event_rows.groupby("original_event_id", sort=False, dropna=False):
        continuity_count = group["continuity_segment_id"].astype("string").dropna().nunique()
        candidate_types = group["candidate_event_type"].astype("string").dropna().unique().tolist()
        priority_reasons = group["candidate_priority_reason"].astype("string").dropna().unique().tolist()
        detailed_types = group["detailed_event_type"].astype("string").dropna().unique().tolist()
        final_labels = group["final_train_label"].astype("string").dropna().unique().tolist()
        if continuity_count != 1:
            problems.append(f"{original_event_id}: continuity_segments={continuity_count}")
        if len(candidate_types) != 1:
            problems.append(f"{original_event_id}: candidate_event_type={candidate_types}")
        if len(priority_reasons) != 1:
            problems.append(f"{original_event_id}: candidate_priority_reason={priority_reasons}")
        if len(detailed_types) != 1:
            problems.append(f"{original_event_id}: detailed_event_type={detailed_types}")
        if len(final_labels) != 1:
            problems.append(f"{original_event_id}: final_train_label={final_labels}")
        if group["candidate_event_type"].isna().any():
            problems.append(f"{original_event_id}: missing candidate_event_type")
        if group["candidate_priority_reason"].isna().any():
            problems.append(f"{original_event_id}: missing candidate_priority_reason")
        if group["detailed_event_type"].isna().any():
            problems.append(f"{original_event_id}: missing detailed_event_type")
        if group["final_train_label"].isna().any():
            problems.append(f"{original_event_id}: missing final_train_label")
    if problems:
        sample = "; ".join(problems[:10])
        raise ValueError(
            "V6 original-event integrity check failed. "
            "Each original_event_id must map to exactly one continuity segment, candidate type, "
            "detailed event type, and final train label. Sample issues: "
            + sample
        )
