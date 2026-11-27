from __future__ import annotations

from itertools import product
from typing import Iterable

import pandas as pd


STATE_VALUES = ("POSITIVE", "NEGATIVE", "NOT_EVALUABLE")


def build_point_contract_replay(
    applicability: pd.DataFrame,
    primitive: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Resolve Phase-B candidate states without touching the label engine."""
    required_app = {
        "record.id",
        "low_target_eligibility",
        "thermal_rule_applicability",
        "rise_rule_applicability",
        "ec_shift_rule_applicability",
    }
    missing = required_app - set(applicability.columns)
    if missing:
        raise KeyError(f"Phase A applicability is missing columns: {sorted(missing)}")
    frame = primitive.merge(
        applicability[list(required_app)],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    flag_columns = ["low_flag", "thermal_flag", "moisture_rise_flag", "ec_shift_flag"]

    def state(value: object) -> str:
        if pd.isna(value):
            return "NOT_EVALUABLE"
        return "POSITIVE" if bool(value) else "NEGATIVE"

    states = pd.DataFrame({f"{column}_state": frame[column].map(state) for column in flag_columns})
    frame = pd.concat([frame.reset_index(drop=True), states], axis=1)
    resolutions: list[str] = []
    reasons: list[str] = []
    candidate_train_eligible: list[bool] = []
    for row in frame.itertuples(index=False):
        low_eligible = bool(getattr(row, "low_target_eligibility", False))
        low_state = getattr(row, "low_flag_state")
        aux_states = [
            getattr(row, "thermal_flag_state"),
            getattr(row, "moisture_rise_flag_state"),
            getattr(row, "ec_shift_flag_state"),
        ]
        if not low_eligible or low_state == "NOT_EVALUABLE":
            resolution, reason, eligible = "POINT_NOT_EVALUABLE", "LOW_TARGET_NOT_EVALUABLE", False
        elif low_state == "POSITIVE":
            resolution, reason, eligible = "LOW", "LOW_DIRECT_EVIDENCE", True
        elif "POSITIVE" in aux_states:
            resolution, reason, eligible = "UNRESOLVED_ENVIRONMENTAL", "OBSERVED_AUXILIARY_POSITIVE", True
        elif "NOT_EVALUABLE" in aux_states:
            resolution, reason, eligible = "POINT_CONTEXT_INCOMPLETE", "REQUIRED_CONTEXT_NOT_EVALUABLE", False
        else:
            resolution, reason, eligible = "REFERENCE", "ALL_REQUIRED_EVIDENCE_NEGATIVE", True
        resolutions.append(resolution)
        reasons.append(reason)
        candidate_train_eligible.append(eligible)
    frame["point_resolution"] = pd.Series(resolutions, dtype="string")
    frame["primary_resolution_reason"] = pd.Series(reasons, dtype="string")
    frame["candidate_train_eligibility"] = pd.Series(candidate_train_eligible, dtype="boolean")
    frame["authority_status"] = "CANDIDATE_ONLY"
    frame["review_required"] = True
    snapshot = (
        frame["point_resolution"]
        .value_counts(dropna=False)
        .rename_axis("point_resolution")
        .reset_index(name="row_count")
    )
    matrix = build_compatibility_matrix(frame)
    return frame.convert_dtypes(), matrix.convert_dtypes(), snapshot.convert_dtypes()


def build_compatibility_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    observed = set(
        zip(
            frame["low_flag_state"].astype(str),
            frame["thermal_flag_state"].astype(str),
            frame["moisture_rise_flag_state"].astype(str),
            frame["ec_shift_flag_state"].astype(str),
        )
    )
    for states in product(STATE_VALUES, repeat=4):
        low, thermal, rise, ec = states
        if low == "NOT_EVALUABLE":
            resolution, reason, eligible = "POINT_NOT_EVALUABLE", "LOW_TARGET_NOT_EVALUABLE", False
        elif low == "POSITIVE":
            resolution, reason, eligible = "LOW", "LOW_DIRECT_EVIDENCE", True
        elif "POSITIVE" in (thermal, rise, ec):
            resolution, reason, eligible = "UNRESOLVED_ENVIRONMENTAL", "OBSERVED_AUXILIARY_POSITIVE", True
        elif "NOT_EVALUABLE" in (thermal, rise, ec):
            resolution, reason, eligible = "POINT_CONTEXT_INCOMPLETE", "REQUIRED_CONTEXT_NOT_EVALUABLE", False
        else:
            resolution, reason, eligible = "REFERENCE", "ALL_REQUIRED_EVIDENCE_NEGATIVE", True
        structural = (low == "NOT_EVALUABLE" and (rise != "NOT_EVALUABLE" or ec != "NOT_EVALUABLE")) or (
            (rise == "NOT_EVALUABLE") != (ec == "NOT_EVALUABLE")
        )
        reachability = "STRUCTURALLY_UNREACHABLE" if structural else (
            "REACHABLE" if states in observed else "UNOBSERVED_IN_E1"
        )
        rows.append(
            {
                "compatibility_row_id": "|".join(states),
                "low_state": low,
                "thermal_state": thermal,
                "rise_state": rise,
                "ec_state": ec,
                "reachability_status": reachability,
                "unreachable_reason": "SHARED_APPLICABILITY_DEPENDENCY" if structural else pd.NA,
                "observed_in_e1": states in observed,
                "resolution_id": resolution,
                "primary_resolution_reason": reason,
                "evidence_tags_preserved": True,
                "candidate_train_eligibility": eligible,
                "authority_status": "CANDIDATE_ONLY",
                "review_required": True,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()
