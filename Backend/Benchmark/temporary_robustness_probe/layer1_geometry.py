from __future__ import annotations

from pathlib import Path

import pandas as pd


PHASE_B_RUN = Path("Backend/Benchmark/weak_labels/artifacts/phase_b/phase_b_decision_pack_20260805_091658")
PHASE_C_ORIGIN = Path(
    "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_unres_origin_split_20260902_213111"
)
Q_CONTRACTS = ("Q05", "Q10", "Q15", "Q20")
PERSISTENCE_KS = (2, 3, 4, 6)


def build_layer1_tables(repo_root: Path) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Build non-training Layer 1 tables from already materialized audit artifacts."""

    operationalization = repo_root / PHASE_B_RUN / "operationalization"
    thresholds = _build_threshold_prevalence(repo_root / PHASE_B_RUN / "thresholds" / "candidate_threshold_audit.csv")
    geometry = pd.read_parquet(operationalization / "qk_geometry.parquet")
    geometry = geometry.loc[
        geometry["q_contract_id"].isin(Q_CONTRACTS)
        & geometry["k"].isin(PERSISTENCE_KS)
        & geometry["operationalization_id"].notna()
    ].copy()
    geometry = geometry.sort_values(["q_contract_id", "k"]).reset_index(drop=True)

    run_lengths, normalized_events = _build_run_length_summary(
        operationalization / "anchor_dependency_audit.parquet"
    )
    event_overlap = _build_event_overlap(normalized_events)
    boundary = _build_boundary_summary(operationalization / "qk_boundary_audit.parquet")
    unres = _build_unresolved_origin(repo_root / PHASE_C_ORIGIN / "unres_origin_assignments.parquet")

    q10 = geometry.loc[geometry["q_contract_id"].eq("Q10")].drop_duplicates("k").set_index("k")
    q10_survival = {
        f"K{int(k)}": float(q10.loc[k, "event_survival_from_k1"])
        for k in PERSISTENCE_KS
        if k in q10.index
    }
    point_prevalence = thresholds["point_prevalence"]
    summary = {
        "status": "diagnostic_layer1_complete",
        "source_status": "candidate_only",
        "selected_q_contracts": list(Q_CONTRACTS),
        "selected_persistence_k": list(PERSISTENCE_KS),
        "point_prevalence": point_prevalence,
        "q10_event_survival_from_k1": q10_survival,
        "geometry_changed_enough_for_layer2": (
            len(set(round(value, 6) for value in point_prevalence.values())) > 1
            and (max(q10_survival.values()) - min(q10_survival.values()) >= 0.1)
        ),
        "boundary_material_shift_observed": bool(boundary["material_shift_count"].sum() > 0),
        "unresolved_origin_counts": unres.set_index("unres_origin")["count"].to_dict(),
        "interpretation_boundary": (
            "This is a geometry/provenance probe. It does not select a primary Q/K "
            "contract and does not establish independent ground truth."
        ),
    }
    tables = {
        "threshold_prevalence": thresholds["table"],
        "selected_geometry": geometry,
        "run_length_summary": run_lengths,
        "event_overlap": event_overlap,
        "boundary_summary": boundary,
        "unresolved_origin": unres,
    }
    return tables, summary


def _build_threshold_prevalence(path: Path) -> dict[str, object]:
    frame = pd.read_csv(path)
    frame = frame.loc[frame["threshold_id"].astype("string").str.match(r"LOW_MOISTURE_Q(05|10|15|20)_")].copy()
    frame["q_contract_id"] = frame["threshold_id"].str.extract(r"(Q\d+)", expand=False)
    frame["point_prevalence"] = frame["positive_count"] / frame["evaluable_count"]
    table = frame[
        [
            "q_contract_id",
            "threshold_value",
            "evaluable_count",
            "positive_count",
            "point_prevalence",
            "missing_or_unevaluable_count",
            "authority_status",
        ]
    ].sort_values("q_contract_id")
    return {
        "table": table.reset_index(drop=True),
        "point_prevalence": {
            str(row.q_contract_id): float(row.point_prevalence) for row in table.itertuples()
        },
    }


def _build_run_length_summary(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_parquet(path)
    frame = frame.loc[
        frame["q_contract_id"].isin(Q_CONTRACTS)
        & frame["persistence_k"].isin(PERSISTENCE_KS)
        & frame["window_horizon_hours"].eq(3)
        & frame["candidate_anchor"].astype(bool)
        & frame["evaluation_usable"].astype(bool)
    ].copy()
    frame["normalized_event_id"] = frame["observed_low_run_id"].astype("string").str.replace(
        r"^[^:]+:", "", regex=True
    )
    events = frame[["q_contract_id", "persistence_k", "normalized_event_id"]].drop_duplicates()
    event_lengths = frame[
        ["q_contract_id", "persistence_k", "normalized_event_id", "run_length"]
    ].drop_duplicates()
    summary = (
        event_lengths.groupby(["q_contract_id", "persistence_k"], as_index=False)
        .agg(
            observed_event_count=("normalized_event_id", "nunique"),
            min_run_length=("run_length", "min"),
            p25_run_length=("run_length", lambda values: values.quantile(0.25)),
            median_run_length=("run_length", "median"),
            mean_run_length=("run_length", "mean"),
            p75_run_length=("run_length", lambda values: values.quantile(0.75)),
            max_run_length=("run_length", "max"),
        )
        .sort_values(["q_contract_id", "persistence_k"])
        .reset_index(drop=True)
    )
    return summary, events


def _build_event_overlap(events: pd.DataFrame) -> pd.DataFrame:
    event_sets = {
        (str(q), int(k)): set(group["normalized_event_id"].astype(str))
        for (q, k), group in events.groupby(["q_contract_id", "persistence_k"])
    }
    baseline = event_sets.get(("Q10", 3), set())
    rows: list[dict[str, object]] = []
    for (q, k), current in sorted(event_sets.items()):
        union = baseline | current
        intersection = baseline & current
        rows.append(
            {
                "q_contract_id": q,
                "persistence_k": k,
                "event_count": len(current),
                "baseline": "Q10-K3",
                "intersection_event_count": len(intersection),
                "union_event_count": len(union),
                "jaccard_vs_q10_k3": len(intersection) / len(union) if union else 1.0,
                "baseline_coverage": len(intersection) / len(baseline) if baseline else 1.0,
            }
        )
    return pd.DataFrame(rows)


def _build_boundary_summary(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    frame = frame.loc[frame["q_contract_id"].isin(Q_CONTRACTS)].copy()
    summary = (
        frame.groupby(["q_contract_id", "boundary_name"], as_index=False)
        .agg(
            fold_count=("fold_id", "nunique"),
            crossing_event_count=("crossing_event_count", "sum"),
            material_shift_count=("material_shift_ge_4_percent", "sum"),
            max_boundary_shift_percent=("max_boundary_shift_percent", "max"),
            review_statuses=("boundary_review_status", lambda values: "|".join(sorted(set(values.astype(str))))),
        )
        .sort_values(["q_contract_id", "boundary_name"])
        .reset_index(drop=True)
    )
    return summary


def _build_unresolved_origin(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    counts = frame["unres_origin"].value_counts(dropna=False).rename_axis("unres_origin").reset_index(name="count")
    counts["share_of_all_anchors"] = counts["count"] / len(frame)
    counts["target_regime"] = "Q10-K3-temporal-3h"
    return counts
