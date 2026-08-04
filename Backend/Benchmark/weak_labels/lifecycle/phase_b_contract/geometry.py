from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.candidate_runs import (
    build_candidate_low_frame,
    load_e1_geometry_frame,
)


def build_qk_geometry(
    canonical_history_path: Path,
    phase_a_run_dir: Path,
    q_values: tuple[tuple[str, float], ...],
    *,
    protocol_registry_run_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = load_e1_geometry_frame(
        canonical_history_path, phase_a_run_dir, protocol_registry_run_dir
    )
    all_rows: list[dict[str, object]] = []
    support_rows: list[dict[str, object]] = []
    folds_path = protocol_registry_run_dir / "folds" / "e1_fold_registry.parquet"
    folds = pd.read_parquet(folds_path) if folds_path.exists() else pd.DataFrame()
    for q_id, threshold in q_values:
        _, runs = build_candidate_low_frame(frame, q_id, threshold)
        runs["event_id"] = runs["observed_low_run_id"]
        max_k = int(runs["run_length"].max()) if not runs.empty else 0
        event_sets: dict[int, set[str]] = {}
        for k in range(1, max_k + 1):
            event_sets[k] = set(runs.loc[runs["run_length"] >= k, "event_id"].astype(str))
            surviving = runs.loc[runs["run_length"] >= k]
            previous = event_sets.get(k - 1, event_sets[k])
            loss_from_k1 = 1.0 - (len(event_sets[k]) / len(event_sets[1])) if event_sets[1] else 1.0
            loss_from_previous = len(previous - event_sets[k])
            support = _fold_support(surviving, folds)
            for _, fold in support.iterrows():
                for role in ("train", "validation", "test"):
                    support_rows.append(
                        {
                            "q_contract_id": q_id,
                            "k": k,
                            "fold_policy_id": fold["fold_policy_id"],
                            "fold_id": fold["fold_id"],
                            "split_role": role,
                            "event_count": int(len(event_sets[k])),
                            "persistent_anchor_count": int(_anchors_in_interval(surviving, fold, role, k)),
                        }
                    )
            all_rows.append(
                {
                    "q_contract_id": q_id,
                    "threshold_value": threshold,
                    "k": k,
                    "raw_event_count": int(len(event_sets[1])),
                    "event_count": int(len(event_sets[k])),
                    "event_survival_from_k1": len(event_sets[k]) / len(event_sets[1]) if event_sets[1] else 0.0,
                    "event_loss_from_k1": loss_from_k1,
                    "event_survival_from_primary": pd.NA,
                    "event_loss_from_primary": pd.NA,
                    "new_event_deaths": int(loss_from_previous),
                    "persistent_anchor_count": int((surviving["run_length"] - k + 1).clip(lower=0).sum()),
                    # Kept for schema compatibility. This is persistence
                    # startup loss, not split-boundary loss; the new anchor
                    # safety artifact owns boundary/purge accounting.
                    "boundary_anchor_loss": int(surviving["run_length"].clip(upper=max(k - 1, 0)).sum()),
                    "persistence_startup_anchor_loss": int(
                        surviving["run_length"].clip(upper=max(k - 1, 0)).sum()
                    ),
                    "max_run_length": max_k,
                    "operationalization_id": f"{q_id}-K{k}",
                    "candidate_status": "CANDIDATE_ONLY",
                }
            )
        if max_k:
            all_rows.extend(_role_rows(q_id, all_rows, max_k))
    return pd.DataFrame(all_rows).convert_dtypes(), pd.DataFrame(support_rows).convert_dtypes()


def _role_rows(q_id: str, rows: list[dict[str, object]], max_k: int) -> list[dict[str, object]]:
    subset = [row for row in rows if row["q_contract_id"] == q_id]
    by_k = {int(row["k"]): row for row in subset}
    roles: list[dict[str, object]] = []
    for role in ("K_SELECTION_REVIEW_REQUIRED", "LOCAL_K_REVIEW_REQUIRED"):
        roles.append(
            {
                "q_contract_id": q_id,
                "k": pd.NA,
                "regime_role": role,
                "support_status": "REVIEW_REQUIRED",
                "selection_reason": "NO_PRIMARY_K_IS_SELECTED_IN_B1",
            }
        )
    upper = 1
    while upper + 1 <= max_k and by_k[upper + 1]["event_count"] == by_k[upper]["event_count"]:
        upper += 1
    roles.append(
        {
            "q_contract_id": q_id,
            "k": upper,
            "regime_role": "LOCAL_UPPER_K",
            "support_status": "AVAILABLE",
            "selection_reason": "EVENT_ID_PLATEAU_END",
        }
    )
    first_death = next((k for k in range(2, max_k + 1) if by_k[k]["new_event_deaths"] > 0), None)
    for role, predicate in (
        ("FIRST_EVENT_DEATH_K", lambda loss: loss > 0),
        ("MODERATE_COLLAPSE_K", lambda loss: 0.30 <= loss <= 0.40),
        ("STRONG_COLLAPSE_K", lambda loss: 0.50 <= loss <= 0.60),
        ("EXTREME_COLLAPSE_K", lambda loss: loss >= 0.70),
    ):
        if role == "FIRST_EVENT_DEATH_K":
            selected = first_death
        else:
            selected = next((k for k in range(2, max_k + 1) if predicate(float(by_k[k]["event_loss_from_k1"]))), None)
        roles.append(
            {
                "q_contract_id": q_id,
                "k": selected if selected is not None else pd.NA,
                "regime_role": role,
                "support_status": "AVAILABLE" if selected is not None else "NO_ADMISSIBLE_K_FOR_ROLE",
                "selection_reason": "CURVE_RULE" if selected is not None else "CURVE_DID_NOT_REACH_ROLE",
            }
        )
    return roles


def _fold_support(runs: pd.DataFrame, folds: pd.DataFrame) -> pd.DataFrame:
    if folds.empty:
        return pd.DataFrame()
    rows = []
    for _, fold in folds.loc[folds["evaluation_usable"].fillna(False).astype(bool)].iterrows():
        rows.append(
            {
                "fold_policy_id": fold["fold_policy_id"],
                "fold_id": fold["fold_id"],
                "train_start": pd.to_datetime(fold["train_start"], utc=True),
                "train_end": pd.to_datetime(fold["train_end"], utc=True),
                "validation_start": pd.to_datetime(fold["validation_start"], utc=True),
                "validation_end": pd.to_datetime(fold["validation_end"], utc=True),
                "test_start": pd.to_datetime(fold["test_start"], utc=True),
                "test_end": pd.to_datetime(fold["test_end"], utc=True),
            }
        )
    return pd.DataFrame(rows)


def _anchors_in_interval(runs: pd.DataFrame, fold: pd.Series, role: str, k: int) -> int:
    start = fold[f"{role}_start"]
    end = fold[f"{role}_end"]
    selected = runs.loc[(runs["end_time"] >= start) & (runs["end_time"] < end), "run_length"]
    return int((selected - k + 1).clip(lower=0).sum())
