from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_e1_geometry_frame(
    canonical_history_path: Path,
    phase_a_run_dir: Path,
    protocol_registry_run_dir: Path,
) -> pd.DataFrame:
    """Load the E1 fields needed by every candidate Q×K analysis.

    This is deliberately limited to candidate geometry inputs. It does not
    materialize labels or read any E2/E3 payload.
    """

    canonical = pd.read_csv(canonical_history_path, low_memory=False)
    applicability = pd.read_parquet(
        phase_a_run_dir / "technical_applicability" / "rule_applicability.parquet"
    )[
        ["record.id", "low_target_eligibility"]
    ]
    strict = pd.read_parquet(
        phase_a_run_dir / "continuity" / "strict_continuity_audit.parquet"
    )[
        [
            "record.id",
            "sample_time",
            "deployment_segment_id",
            "strict_continuity_id",
        ]
    ]
    required = ["record.id", "record.sample_time_local", "npk.soil_moisture_pct"]
    missing = [column for column in required if column not in canonical.columns]
    if missing:
        raise KeyError(f"Canonical history is missing geometry columns: {missing}")
    if canonical["record.id"].duplicated().any():
        raise ValueError("Canonical record.id must be globally unique for B1 geometry.")

    frame = canonical[required].merge(
        applicability, on="record.id", validate="one_to_one"
    ).merge(strict, on="record.id", validate="one_to_one")
    frame["sample_time"] = pd.to_datetime(
        frame["record.sample_time_local"], errors="coerce", utc=True
    )
    environment_manifest = pd.read_csv(
        protocol_registry_run_dir / "environment" / "environment_manifest.csv"
    )
    e1_rows = environment_manifest.loc[
        environment_manifest["environment_id"].astype(str) == "E1"
    ]
    if len(e1_rows) != 1:
        raise ValueError("Protocol registry must contain exactly one E1 environment.")
    e1 = e1_rows.iloc[0]
    e1_start = pd.to_datetime(e1["start_time"], utc=True)
    e1_end = pd.to_datetime(e1["end_time"], utc=True)
    return (
        frame.loc[
            frame["sample_time"].notna()
            & (frame["sample_time"] >= e1_start)
            & (frame["sample_time"] < e1_end)
        ]
        .sort_values(["sample_time", "record.id"])
        .reset_index(drop=True)
    )


def build_candidate_low_frame(
    frame: pd.DataFrame, q_id: str, threshold: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build low flags, run positions, and intrinsic observed runs for one Q."""

    working = frame.copy()
    moisture = pd.to_numeric(working["npk.soil_moisture_pct"], errors="coerce")
    working["low"] = working["low_target_eligibility"].fillna(False).astype(bool) & moisture.le(
        threshold
    )
    working["non_low_block"] = working.groupby("strict_continuity_id", dropna=False)["low"].transform(
        lambda values: (~values).cumsum()
    )
    low = working.loc[working["low"]].copy()
    if low.empty:
        return working, pd.DataFrame(
            columns=[
                "q_contract_id",
                "strict_continuity_id",
                "non_low_block",
                "observed_low_run_id",
                "run_length",
                "start_time",
                "end_time",
            ]
        )
    low["run_position"] = low.groupby(
        ["strict_continuity_id", "non_low_block"], dropna=False
    ).cumcount() + 1
    low["run_length"] = low.groupby(
        ["strict_continuity_id", "non_low_block"], dropna=False
    )["record.id"].transform("size")
    low["observed_low_run_id"] = low.apply(
        lambda row: f"{q_id}:{row['strict_continuity_id']}:{int(row['non_low_block'])}",
        axis=1,
    )
    working = working.merge(
        low[
            [
                "record.id",
                "observed_low_run_id",
                "run_position",
                "run_length",
            ]
        ],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    runs = (
        low.groupby(
            ["strict_continuity_id", "non_low_block", "observed_low_run_id"],
            dropna=False,
        )
        .agg(
            run_length=("record.id", "size"),
            start_time=("sample_time", "min"),
            end_time=("sample_time", "max"),
            deployment_segment_id=("deployment_segment_id", "first"),
        )
        .reset_index()
    )
    runs["q_contract_id"] = q_id
    return working, runs
