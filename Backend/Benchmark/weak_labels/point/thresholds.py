from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.shared.weak_rules import (
    LowRelativeMoistureThresholds,
    fit_low_relative_moisture_thresholds,
)
from Backend.Benchmark.weak_labels.runtime.contracts import ThresholdRecord
from Backend.Benchmark.weak_labels.shared.configs import (
    MOISTURE_RISE_DELTA_PP,
    PERSISTENT_LOW_RUN_MIN_STEPS,
    THERMAL_EVIDENCE_THRESHOLD_KPA,
    THRESHOLD_MODE_TRAIN_FITTED_GLOBAL,
    THRESHOLD_MODE_TRAIN_FITTED_SEGMENT,
    WEAK_LABELS_VERSION,
)
from Backend.Benchmark.weak_labels.shared.helpers import hash_dataframe_rows


@dataclass(frozen=True)
class ThresholdContext:
    threshold_mode: str
    low_moisture_global: LowRelativeMoistureThresholds
    low_moisture_by_segment: dict[str, LowRelativeMoistureThresholds]
    ec_shift_abs_delta_q95: float | None
    threshold_records: tuple[ThresholdRecord, ...]
    sensitivity_df: pd.DataFrame

    def resolve_low_moisture_threshold(self, segment_id: str) -> LowRelativeMoistureThresholds:
        if self.threshold_mode == THRESHOLD_MODE_TRAIN_FITTED_SEGMENT and segment_id in self.low_moisture_by_segment:
            return self.low_moisture_by_segment[segment_id]
        return self.low_moisture_global


def build_threshold_context(
    continuity_df: pd.DataFrame,
    *,
    threshold_mode: str,
) -> ThresholdContext:
    train_df = continuity_df.loc[continuity_df["base_partition"] == "train"].copy()
    moisture_train = pd.to_numeric(
        train_df.loc[train_df["low_moisture_applicable"], "npk.soil_moisture_pct"],
        errors="coerce",
    ).dropna()
    if moisture_train.empty:
        raise ValueError("weak_labels could not fit train-only low-moisture thresholds because no applicable train rows exist.")

    low_global = fit_low_relative_moisture_thresholds(moisture_train, scope_key="global_train")
    low_by_segment: dict[str, LowRelativeMoistureThresholds] = {}
    threshold_records: list[ThresholdRecord] = [
        ThresholdRecord(
            threshold_id="low_relative_moisture_q10_global",
            threshold_version=WEAK_LABELS_VERSION,
            fit_mode=threshold_mode,
            source_fields=("npk.soil_moisture_pct",),
            fit_partition="train",
            fit_record_count=int(len(moisture_train)),
            fit_record_hash=_hash_threshold_rows(
                train_df.loc[train_df["low_moisture_applicable"], ["record.id", "npk.soil_moisture_pct"]]
            ),
            segment_scope="global",
            value=float(low_global.q10),
            notes="Primary low-relative-moisture cutoff reused across point and V2 labels.",
        ),
    ]
    if threshold_mode == THRESHOLD_MODE_TRAIN_FITTED_SEGMENT:
        for segment_id, group in train_df.groupby("record.segment_id", sort=False, dropna=False):
            segment_values = pd.to_numeric(
                group.loc[group["low_moisture_applicable"], "npk.soil_moisture_pct"],
                errors="coerce",
            ).dropna()
            if segment_values.empty:
                continue
            low_by_segment[str(segment_id)] = fit_low_relative_moisture_thresholds(segment_values, scope_key=str(segment_id))
            threshold_records.append(
                ThresholdRecord(
                    threshold_id=f"low_relative_moisture_q10_{segment_id}",
                    threshold_version=WEAK_LABELS_VERSION,
                    fit_mode=threshold_mode,
                    source_fields=("npk.soil_moisture_pct",),
                    fit_partition="train",
                    fit_record_count=int(len(segment_values)),
                    fit_record_hash=_hash_threshold_rows(
                        group.loc[group["low_moisture_applicable"], ["record.id", "npk.soil_moisture_pct"]]
                    ),
                    segment_scope=str(segment_id),
                    value=float(low_by_segment[str(segment_id)].q10),
                    notes="Segment-scoped low-relative-moisture cutoff fit on train rows only.",
                )
            )

    ec_shift_abs_delta_q95 = _fit_ec_shift_abs_delta_q95(train_df)
    if ec_shift_abs_delta_q95 is not None:
        threshold_records.append(
            ThresholdRecord(
                threshold_id="ec_shift_abs_delta_q95_global",
                threshold_version=WEAK_LABELS_VERSION,
                fit_mode=THRESHOLD_MODE_TRAIN_FITTED_GLOBAL,
                source_fields=("npk.ec",),
                fit_partition="train",
                fit_record_count=int(train_df.loc[train_df["ec_shift_delta_abs"].notna(), "record.id"].nunique()),
                fit_record_hash=_hash_threshold_rows(
                    train_df.loc[train_df["ec_shift_delta_abs"].notna(), ["record.id", "ec_shift_delta_abs"]]
                ),
                segment_scope="global",
                value=float(ec_shift_abs_delta_q95),
                notes="Train-fitted EC shift proxy cutoff.",
            )
        )

    threshold_records.extend(
        [
            ThresholdRecord(
                threshold_id="persistent_low_run_min_steps",
                threshold_version=WEAK_LABELS_VERSION,
                fit_mode="FIXED_REPOSITORY",
                source_fields=("point.low_relative_moisture_flag",),
                fit_partition="none",
                fit_record_count=0,
                fit_record_hash="fixed",
                segment_scope="global",
                value=float(PERSISTENT_LOW_RUN_MIN_STEPS),
                notes="Fixed persistence minimum for V2 temporal labels.",
            ),
            ThresholdRecord(
                threshold_id="rapid_wetting_delta_pp",
                threshold_version=WEAK_LABELS_VERSION,
                fit_mode="FIXED_REPOSITORY",
                source_fields=("npk.soil_moisture_pct",),
                fit_partition="none",
                fit_record_count=0,
                fit_record_hash="fixed",
                segment_scope="global",
                value=float(MOISTURE_RISE_DELTA_PP),
                notes="Fixed moisture-rise sensitivity threshold.",
            ),
            ThresholdRecord(
                threshold_id="thermal_vpd_threshold_kpa",
                threshold_version=WEAK_LABELS_VERSION,
                fit_mode="FIXED_REPOSITORY",
                source_fields=("sht.temp_c", "sht.humidity_pct"),
                fit_partition="none",
                fit_record_count=0,
                fit_record_hash="fixed",
                segment_scope="global",
                value=float(THERMAL_EVIDENCE_THRESHOLD_KPA),
                notes="Fixed thermal-dry-air threshold for point evidence.",
            ),
        ]
    )

    sensitivity_rows = [
        {
            "threshold_id": "low_relative_moisture_quantiles",
            "fit_partition": "train",
            "fit_record_count": int(len(moisture_train)),
            "q05": float(moisture_train.quantile(0.05)),
            "q10": float(moisture_train.quantile(0.10)),
            "q15": float(moisture_train.quantile(0.15)),
            "q20": float(moisture_train.quantile(0.20)),
        }
    ]
    if ec_shift_abs_delta_q95 is not None:
        ec_shift_values = pd.to_numeric(train_df["ec_shift_delta_abs"], errors="coerce").dropna()
        sensitivity_rows.append(
            {
                "threshold_id": "ec_shift_abs_delta_quantiles",
                "fit_partition": "train",
                "fit_record_count": int(len(ec_shift_values)),
                "q05": float(ec_shift_values.quantile(0.05)),
                "q10": float(ec_shift_values.quantile(0.10)),
                "q15": float(ec_shift_values.quantile(0.15)),
                "q20": float(ec_shift_values.quantile(0.20)),
            }
        )
    return ThresholdContext(
        threshold_mode=threshold_mode,
        low_moisture_global=low_global,
        low_moisture_by_segment=low_by_segment,
        ec_shift_abs_delta_q95=ec_shift_abs_delta_q95,
        threshold_records=tuple(threshold_records),
        sensitivity_df=pd.DataFrame(sensitivity_rows).convert_dtypes(),
    )


def _fit_ec_shift_abs_delta_q95(train_df: pd.DataFrame) -> float | None:
    ec_shift_values = pd.to_numeric(train_df["ec_shift_delta_abs"], errors="coerce").dropna()
    if ec_shift_values.empty:
        return None
    return float(ec_shift_values.quantile(0.95))


def _hash_threshold_rows(dataframe: pd.DataFrame) -> str:
    if dataframe.empty:
        return "empty"
    return hash_dataframe_rows(dataframe.astype("string"))
