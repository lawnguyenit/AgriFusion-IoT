from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .history import FeatureBundle
from .representations import RepresentationBundle


MOISTURE = "npk.soil_moisture_pct"
SNAPSHOT_ID = "S1_X_t"
CORE_IDS = (
    "S0_M_t",
    "S1_X_t",
    "B_M",
    "S2_X_t_HM",
    "S3_X_t_HX",
    "F01_X_t_WX",
    "F11_X_t_HX_WX",
    "S3_X_HX_T",
    "F11_X_HX_WX_T",
    "A_only",
    "S3_X_HX_A",
    "S3_X_HX_N45",
)
PROBE_IDS = ("S0_M_t", "S1_X_t", "S2_X_t_HM", "S3_X_t_HX")
PROBE_LABELS = ("d_0", "d_1", "d_2", "d_ge_3")


@dataclass(frozen=True)
class ProgramRepresentationSet:
    representations: dict[str, RepresentationBundle]
    block_contract: dict[str, object]


def build_program_representations(
    *,
    snapshot_bundle: FeatureBundle,
    window_bundle: FeatureBundle,
    history_bundle: FeatureBundle,
    nested: dict[str, RepresentationBundle],
    row_index: pd.DataFrame,
    window_audit: pd.DataFrame,
    negative_seed: int,
) -> ProgramRepresentationSet:
    snapshot_names = list(snapshot_bundle.feature_names)
    window_names = list(window_bundle.feature_names)
    context_names = [name for name in window_names if name not in snapshot_names]
    moisture_lags = [f"{MOISTURE}__causal_lag_{lag}" for lag in range(1, 13)]
    sensor_lags = [name for name in history_bundle.feature_names if "__causal_lag_" in name]
    supporting_names = [name for name in snapshot_names if name != MOISTURE]
    supporting_lags = [name for name in sensor_lags if not name.startswith(f"{MOISTURE}__")]
    if len(snapshot_names) != 9 or len(supporting_names) != 8:
        raise ValueError("RQ1 program requires a 9-channel snapshot with one defining moisture channel.")
    if len(moisture_lags) != 12 or len(supporting_lags) != 96 or len(context_names) != 45:
        raise ValueError(
            f"RQ1 program block drift: moisture_lags={len(moisture_lags)}, "
            f"supporting_lags={len(supporting_lags)}, window_summaries={len(context_names)}"
        )

    t_frame, t_names = _build_temporal_context(history_bundle=history_bundle, row_index=row_index, window_audit=window_audit)
    a_frame, a_names, a_capability = _build_acquisition_evidence(
        snapshot_bundle=snapshot_bundle,
        history_bundle=history_bundle,
        window_audit=window_audit,
    )
    negative_frame, negative_names = _build_negative_control(
        source=window_bundle.frame.loc[:, ["sample_id", *context_names]],
        context_names=context_names,
        seed=negative_seed,
    )

    representations: dict[str, RepresentationBundle] = {
        "S0_M_t": _select(nested["S0_M_t"].feature_bundle, "S0_M_t", [MOISTURE], {"D": [MOISTURE]}),
        "S1_X_t": _select(nested["S1_X_t"].feature_bundle, "S1_X_t", snapshot_names, {"D": [MOISTURE], "C": supporting_names}),
        "B_M": _select(nested["B_M"].feature_bundle, "B_M", [MOISTURE, *moisture_lags], {"D": [MOISTURE], "H_D": moisture_lags}),
        "S2_X_t_HM": _select(nested["S2_X_t_HM"].feature_bundle, "S2_X_t_HM", [*snapshot_names, *moisture_lags], {"D": [MOISTURE], "C": supporting_names, "H_D": moisture_lags}),
        "S3_X_t_HX": _select(nested["S3_X_t_HX"].feature_bundle, "S3_X_t_HX", [*snapshot_names, *sensor_lags], {"D": [MOISTURE], "C": supporting_names, "H_D": moisture_lags, "H_C": supporting_lags}),
        "F01_X_t_WX": _select(window_bundle, "F01_X_t_WX", [*snapshot_names, *context_names], {"D": [MOISTURE], "C": supporting_names, "W_D/W_C": context_names}),
        "F11_X_t_HX_WX": _select(nested["S4_X_t_HX_C"].feature_bundle, "F11_X_t_HX_WX", [*snapshot_names, *sensor_lags, *context_names], {"D": [MOISTURE], "C": supporting_names, "H_D": moisture_lags, "H_C": supporting_lags, "W_D/W_C": context_names}),
        "A_only": _bundle_from_frame(a_frame, "A_only", a_names, {"A": a_names}, display_name="acquisition_evidence_only"),
        "S3_X_HX_A": _merge_bundle(nested["S3_X_t_HX"].feature_bundle, a_frame, "S3_X_HX_A", {"S3": nested["S3_X_t_HX"].feature_bundle.feature_names, "A": a_names}),
        "S3_X_HX_N45": _merge_bundle(nested["S3_X_t_HX"].feature_bundle, negative_frame, "S3_X_HX_N45", {"S3": nested["S3_X_t_HX"].feature_bundle.feature_names, "N45": negative_names}),
        "S3_X_HX_T": _merge_bundle(nested["S3_X_t_HX"].feature_bundle, t_frame, "S3_X_HX_T", {"S3": nested["S3_X_t_HX"].feature_bundle.feature_names, "T": t_names}),
        "F11_X_HX_WX_T": _merge_bundle(nested["S4_X_t_HX_C"].feature_bundle, t_frame, "F11_X_HX_WX_T", {"F11": nested["S4_X_t_HX_C"].feature_bundle.feature_names, "T": t_names}),
    }
    contract = {
        "defining_block": {"id": "D", "features": [MOISTURE], "count": 1},
        "current_support_block": {"id": "C", "features": supporting_names, "count": len(supporting_names)},
        "defining_history_block": {"id": "H_D", "features": moisture_lags, "count": len(moisture_lags)},
        "support_history_block": {"id": "H_C", "features": supporting_lags, "count": len(supporting_lags)},
        "window_summary_block": {"id": "W_D_W_C", "features": context_names, "count": len(context_names), "derived_from": "causal 3h sensor window"},
        "true_temporal_block": {"id": "T", "features": t_names, "count": len(t_names), "derived_from": "row timestamps, causal history ages, continuity and gap audit"},
        "acquisition_block": {"id": "A", "features": a_names, "count": len(a_names), "capability": a_capability},
        "negative_control": {"id": "N45", "features": negative_names, "count": len(negative_names), "method": "independent deterministic within-column permutation of W_X values; label-independent"},
        "representations": {
            key: {
                "feature_count": len(value.feature_bundle.feature_names),
                "feature_groups": value.feature_bundle.metadata.get("feature_groups", {}),
                "feature_names": value.feature_bundle.feature_names,
            }
            for key, value in representations.items()
        },
    }
    return ProgramRepresentationSet(representations=representations, block_contract=contract)


def add_persistence_probe_target(target_frame: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    output = target_frame.copy()
    depth = pd.to_numeric(output["support_depth_at_anchor"], errors="coerce").fillna(0).astype(int)
    clipped = depth.clip(upper=k)
    output["persistence_state"] = clipped.map({0: "d_0", 1: "d_1", 2: "d_2", 3: "d_ge_3"}).astype("string")
    return output


def _build_temporal_context(*, history_bundle: FeatureBundle, row_index: pd.DataFrame, window_audit: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    history_names = [
        name
        for name in history_bundle.feature_names
        if name.startswith("causal_history__lag_")
        or name in {
            "causal_history__3h_prior_row_count",
            "causal_history__3h_prior_span_hours",
            "causal_history__3h_max_internal_gap_hours",
        }
    ]
    if not history_names:
        raise ValueError("No causal temporal metadata was found for T.")
    ordered = row_index.loc[:, ["record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position", "record.segment_boundary_before"]].copy()
    ordered = ordered.sort_values(["record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"], kind="stable")
    ordered["T__previous_delta_hours"] = ordered.groupby(["record.node_id", "record.segment_id"], dropna=False)["record.ts_sample"].diff() / 3600.0
    ordered["T__segment_boundary_before"] = ordered["record.segment_boundary_before"].fillna(False).astype(int)
    t_extra = ordered.rename(columns={"record.id": "sample_id"}).loc[:, ["sample_id", "T__previous_delta_hours", "T__segment_boundary_before"]]
    audit = window_audit.rename(columns={"record.id": "sample_id"}).loc[:, ["sample_id", "3h_continuity_reset_count", "3h_max_internal_elapsed_gap_sec", "3h_actual_window_span_sec"]].copy()
    audit = audit.rename(columns={"3h_continuity_reset_count": "T__3h_continuity_reset_count", "3h_max_internal_elapsed_gap_sec": "T__3h_max_internal_gap_sec", "3h_actual_window_span_sec": "T__3h_actual_window_span_sec"})
    frame = history_bundle.frame.loc[:, ["sample_id", *history_names]].merge(t_extra, on="sample_id", how="inner", validate="one_to_one").merge(audit, on="sample_id", how="inner", validate="one_to_one")
    names = [*history_names, "T__previous_delta_hours", "T__segment_boundary_before", "T__3h_continuity_reset_count", "T__3h_max_internal_gap_sec", "T__3h_actual_window_span_sec"]
    frame.loc[:, names] = frame.loc[:, names].apply(pd.to_numeric, errors="coerce")
    return frame.convert_dtypes(), names


def _build_acquisition_evidence(*, snapshot_bundle: FeatureBundle, history_bundle: FeatureBundle, window_audit: pd.DataFrame) -> tuple[pd.DataFrame, list[str], dict[str, object]]:
    audit = window_audit.copy()
    audit = audit.rename(columns={"record.id": "sample_id"})
    numeric_names = [
        column
        for column in audit.columns
        if column in {"current_row_complete", "3h_valid_observation_count", "3h_actual_window_span_sec", "3h_span_coverage_ratio", "3h_max_internal_gap_sec", "3h_continuity_reset_count", "3h_eligible_for_training", "3h_expected_observation_count"}
        or column.endswith(("valid_observation_count", "expected_observation_coverage_ratio", "coverage_ratio", "actual_window_span_sec", "count_requirement_satisfied", "span_requirement_satisfied", "insufficient_history"))
    ]
    snapshot = snapshot_bundle.frame.set_index("sample_id")
    missing_names: list[str] = []
    missing_frame = pd.DataFrame(index=snapshot.index)
    for column in snapshot_bundle.feature_names:
        name = f"A__current_missing__{column}"
        missing_names.append(name)
        missing_frame[name] = snapshot[column].isna().astype(int)
    audit_frame = audit.loc[:, ["sample_id", *numeric_names]].copy()
    audit_frame = audit_frame.set_index("sample_id").apply(pd.to_numeric, errors="coerce")
    audit_frame.columns = [f"A__{column}" for column in audit_frame.columns]
    audit_names = list(audit_frame.columns)
    history_quality_names = ["causal_history__3h_prior_valid_row_count", "causal_history__3h_missing_lag_count"]
    history_quality = history_bundle.frame.loc[:, ["sample_id", *history_quality_names]].set_index("sample_id").apply(pd.to_numeric, errors="coerce")
    history_quality.columns = [f"A__{column}" for column in history_quality.columns]
    history_quality_names_prefixed = list(history_quality.columns)
    frame = pd.concat([missing_frame, audit_frame, history_quality], axis=1).reset_index()
    names = [*missing_names, *audit_names, *history_quality_names_prefixed]
    capability = {
        "available": ["current_missingness", "history_validity", "missing_lag_count", "window_validity", "window_coverage", "continuity_reset", "internal_gap"],
        "unsupported": ["rssi", "signal_quality", "firebase_replay", "buffer_delay", "server_upload_delta"],
    }
    return frame.convert_dtypes(), names, capability


def _build_negative_control(*, source: pd.DataFrame, context_names: list[str], seed: int) -> tuple[pd.DataFrame, list[str]]:
    rng = np.random.default_rng(seed)
    output = pd.DataFrame({"sample_id": source["sample_id"].astype("string")})
    names: list[str] = []
    for index, column in enumerate(context_names):
        values = pd.to_numeric(source[column], errors="coerce").to_numpy(dtype=float)
        shuffled = values.copy()
        finite = np.isfinite(shuffled)
        finite_values = shuffled[finite]
        if len(finite_values) > 1:
            shuffled[finite] = finite_values[rng.permutation(len(finite_values))]
        name = f"N45__{index + 1:02d}"
        output[name] = shuffled
        names.append(name)
    return output.convert_dtypes(), names


def _select(source: FeatureBundle, representation_id: str, names: list[str], groups: dict[str, list[str]]) -> RepresentationBundle:
    return _bundle_from_frame(source.frame.loc[:, ["sample_id", *names]], representation_id, names, groups, display_name=representation_id)


def _bundle_from_frame(frame: pd.DataFrame, representation_id: str, names: list[str], groups: dict[str, list[str]], *, display_name: str | None = None) -> RepresentationBundle:
    missing = sorted(set(names).difference(frame.columns))
    if missing:
        raise ValueError(f"{representation_id} is missing feature fields: {missing[:5]}")
    return RepresentationBundle(
        representation_id=representation_id,
        display_name=display_name or representation_id,
        feature_bundle=FeatureBundle(
            frame=frame.loc[:, ["sample_id", *names]].convert_dtypes(),
            feature_names=names,
            metadata={
                "representation_id": representation_id,
                "representation": display_name or representation_id,
                "feature_count": len(names),
                "feature_groups": groups,
                "future_used": False,
                "target_derived_features": False,
                "acquisition_metadata_included": any(key in groups for key in ("A", "T")),
            },
        ),
    )


def _merge_bundle(source: FeatureBundle, extra: pd.DataFrame, representation_id: str, groups: dict[str, list[str]]) -> RepresentationBundle:
    extra_names = [column for column in extra.columns if column != "sample_id"]
    merged = source.frame.merge(extra, on="sample_id", how="inner", validate="one_to_one")
    names = [*source.feature_names, *extra_names]
    return _bundle_from_frame(merged, representation_id, names, groups, display_name=representation_id)
