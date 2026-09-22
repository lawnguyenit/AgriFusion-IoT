import json

import pandas as pd

from Backend.Benchmark.model_suite.analysis.provenance_strata_analysis_data import (
    LOW_LABEL,
    REF_LABEL,
    UNRES_LABEL,
    build_event_online_probability_deltas,
    build_k_contrasts,
    build_k_decomposition,
    build_prediction_count_summary,
    build_prediction_transitions,
    build_probability_summary,
    build_provenance_frame,
    build_provenance_summary,
    build_row_normalized_rates,
    join_predictions_with_provenance,
    pair_event_online_predictions,
    select_predictions,
)


def test_provenance_strata_contract_and_k_states():
    targets = _target_rows()
    provenance = build_provenance_frame(targets)

    assert set(provenance["provenance_stratum"]) == {
        "LOW",
        "U_K_succ",
        "U_K_fail",
        "U_A",
        "REF",
    }
    assert provenance.set_index("provenance_stratum").loc["U_K_succ", "event_target_display"] == "LOW"
    assert provenance.set_index("provenance_stratum").loc["U_K_fail", "event_target_display"] == "UNRES"
    assert provenance.set_index("provenance_stratum").loc["U_A", "event_target_display"] == "UNRES"
    assert build_provenance_summary(provenance)["row_count"].sum() == 5


def test_prediction_summaries_keep_five_strata_and_three_outputs():
    targets = _target_rows()
    provenance = build_provenance_frame(targets)
    predictions = _prediction_rows()
    online = select_predictions(
        predictions,
        target_view_id="temporal_online_3h",
        feature_view_ids=("v2_temporal_mini_3h",),
        partitions=("test",),
    )
    event = select_predictions(
        predictions,
        target_view_id="temporal_event_3h",
        feature_view_ids=("v2_temporal_mini_3h",),
        partitions=("test",),
    )
    online_joined = join_predictions_with_provenance(online, provenance, prediction_source="online")
    event_joined = join_predictions_with_provenance(event, provenance, prediction_source="event")
    counts = build_prediction_count_summary(online_joined)
    rates = build_row_normalized_rates(counts)
    probabilities = build_probability_summary(online_joined)
    decomposition = build_k_decomposition(online_joined)
    contrasts = build_k_contrasts(decomposition)
    paired = pair_event_online_predictions(online, event, provenance)
    deltas = build_event_online_probability_deltas(paired)
    transitions = build_prediction_transitions(paired)

    assert len(counts) == 15
    assert len(rates) == 5
    assert len(probabilities) == 5
    assert rates["support"].tolist() == [1, 1, 1, 1, 1]
    assert set(decomposition["provenance_stratum"]) == {"LOW", "U_K_succ", "U_K_fail"}
    assert len(contrasts) == 1
    assert len(deltas) == 5
    assert not transitions.empty


def test_u_a_requires_q_negative_auxiliary_evidence():
    targets = _target_rows()
    targets.loc[targets["unres_origin"].eq("UNRES_A"), "aux_positive_count"] = 0
    try:
        build_provenance_frame(targets)
    except ValueError as exc:
        assert "auxiliary positive" in str(exc)
    else:
        raise AssertionError("Expected U_A auxiliary evidence validation to fail")


def _target_rows() -> pd.DataFrame:
    rows = [
        _target("s_low", LOW_LABEL, LOW_LABEL, "M_t<=Q", 3, 3, True, "UNRES_NONE", 0),
        _target("s_ks", UNRES_LABEL, LOW_LABEL, "M_t<=Q", 1, 3, True, "UNRES_K", 0),
        _target("s_kf", UNRES_LABEL, UNRES_LABEL, "M_t<=Q", 1, 2, True, "UNRES_K", 0),
        _target("s_a", UNRES_LABEL, UNRES_LABEL, "M_t>Q", 0, None, False, "UNRES_A", 1),
        _target("s_ref", REF_LABEL, REF_LABEL, "M_t>Q", 0, None, False, "NONE", 0),
    ]
    return pd.DataFrame(rows)


def _target(sample_id, online, event, relation, depth, eventual, complete, origin, aux):
    return {
        "sample_id": sample_id,
        "target_view_id": "temporal_online_3h",
        "online_label_name": online,
        "online_label_status": "LABELED",
        "event_label_name": event,
        "event_label_status": "LABELED",
        "point_label": "low_relative_moisture_point" if relation == "M_t<=Q" else "reference_context_at_anchor",
        "unres_origin": origin,
        "m_relation_to_q": relation,
        "aux_positive_count": aux,
        "support_depth_at_anchor": depth,
        "eventual_run_length": eventual,
        "run_complete": complete,
        "required_k": 3,
        "run_id": f"run_{sample_id}",
        "sample_time_utc": f"2026-01-01T00:0{len(sample_id)}:00Z",
        "deployment_segment_id": "seg_1",
    }


def _prediction_rows() -> pd.DataFrame:
    classes = [LOW_LABEL, REF_LABEL, UNRES_LABEL]
    rows = []
    for target_view_id in ("temporal_online_3h", "temporal_event_3h"):
        for sample_id, predicted in (("s_low", LOW_LABEL), ("s_ks", UNRES_LABEL), ("s_kf", UNRES_LABEL), ("s_a", UNRES_LABEL), ("s_ref", REF_LABEL)):
            probability = {label: (1.0 if label == predicted else 0.0) for label in classes}
            rows.append(
                {
                    "target_view_id": target_view_id,
                    "feature_view_id": "v2_temporal_mini_3h",
                    "partition": "test",
                    "fold_id": "fold_1",
                    "sample_id": sample_id,
                    "label_name_pred": predicted,
                    "class_names_json": json.dumps(classes),
                    "prediction_probability_json": json.dumps(probability),
                }
            )
    return pd.DataFrame(rows)
