from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Backend.Benchmark.context_benchmark.src.config.settings import ContextBenchmarkConfig
from Backend.Benchmark.context_benchmark.src.data.canonical_builder import build_real_canonical
from Backend.Benchmark.context_benchmark.src.data.splitting import split_real_dataset


@dataclass(frozen=True)
class RealTrainSizingTarget:
    real_train_row_count: int
    target_total_records: int
    multiplier: float
    real_event_csv: Path
    label_scheme: str
    train_ratio: float
    validation_ratio: float
    test_ratio: float
    purge_gap_minutes: int
    split_strategy: str
    total_real_row_count: int | None = None
    source: str = "estimated_from_real_split"

    def to_manifest_dict(self) -> dict[str, object]:
        return {
            "enabled": True,
            "source": self.source,
            "real_train_row_count": self.real_train_row_count,
            "target_total_records": self.target_total_records,
            "multiplier": self.multiplier,
            "real_event_csv": str(self.real_event_csv),
            "label_scheme": self.label_scheme,
            "train_ratio": self.train_ratio,
            "validation_ratio": self.validation_ratio,
            "test_ratio": self.test_ratio,
            "purge_gap_minutes": self.purge_gap_minutes,
            "split_strategy": self.split_strategy,
            "total_real_row_count": self.total_real_row_count,
        }


def estimate_real_train_sizing_target(
    *,
    multiplier: float,
    real_event_csv: Path | None = None,
    label_scheme: str | None = None,
    train_ratio: float | None = None,
    validation_ratio: float | None = None,
    test_ratio: float | None = None,
    purge_gap_minutes: int | None = None,
    split_strategy: str | None = None,
) -> RealTrainSizingTarget:
    if multiplier <= 0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")

    defaults = ContextBenchmarkConfig()
    resolved_label_scheme = label_scheme or defaults.label_scheme
    resolved_real_event_csv = (real_event_csv or defaults.real_event_csv).resolve()
    resolved_train_ratio = defaults.train_ratio if train_ratio is None else train_ratio
    resolved_validation_ratio = defaults.validation_ratio if validation_ratio is None else validation_ratio
    resolved_test_ratio = defaults.test_ratio if test_ratio is None else test_ratio
    resolved_purge_gap_minutes = defaults.purge_gap_minutes if purge_gap_minutes is None else purge_gap_minutes
    resolved_split_strategy = defaults.split_strategy if split_strategy is None else split_strategy

    real_df = build_real_canonical(resolved_real_event_csv, resolved_label_scheme)
    splits = split_real_dataset(
        real_df=real_df,
        train_ratio=resolved_train_ratio,
        validation_ratio=resolved_validation_ratio,
        test_ratio=resolved_test_ratio,
        purge_gap_minutes=resolved_purge_gap_minutes,
        split_strategy=resolved_split_strategy,
    )
    real_train_row_count = int(len(splits["train"]))
    target_total_records = max(1, int(round(real_train_row_count * multiplier)))
    return RealTrainSizingTarget(
        real_train_row_count=real_train_row_count,
        target_total_records=target_total_records,
        multiplier=multiplier,
        real_event_csv=resolved_real_event_csv,
        label_scheme=resolved_label_scheme,
        train_ratio=resolved_train_ratio,
        validation_ratio=resolved_validation_ratio,
        test_ratio=resolved_test_ratio,
        purge_gap_minutes=resolved_purge_gap_minutes,
        split_strategy=resolved_split_strategy,
        total_real_row_count=int(len(real_df)),
    )


def build_explicit_real_train_sizing_target(
    *,
    real_train_row_count: int,
    multiplier: float,
    real_event_csv: Path | None = None,
    label_scheme: str | None = None,
    train_ratio: float | None = None,
    validation_ratio: float | None = None,
    test_ratio: float | None = None,
    purge_gap_minutes: int | None = None,
    split_strategy: str | None = None,
) -> RealTrainSizingTarget:
    if real_train_row_count <= 0:
        raise ValueError(f"real_train_row_count must be positive, got {real_train_row_count}")
    if multiplier <= 0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")

    defaults = ContextBenchmarkConfig()
    resolved_label_scheme = label_scheme or defaults.label_scheme
    resolved_real_event_csv = (real_event_csv or defaults.real_event_csv).resolve()
    resolved_train_ratio = defaults.train_ratio if train_ratio is None else train_ratio
    resolved_validation_ratio = defaults.validation_ratio if validation_ratio is None else validation_ratio
    resolved_test_ratio = defaults.test_ratio if test_ratio is None else test_ratio
    resolved_purge_gap_minutes = defaults.purge_gap_minutes if purge_gap_minutes is None else purge_gap_minutes
    resolved_split_strategy = defaults.split_strategy if split_strategy is None else split_strategy

    return RealTrainSizingTarget(
        real_train_row_count=real_train_row_count,
        target_total_records=max(1, int(round(real_train_row_count * multiplier))),
        multiplier=multiplier,
        real_event_csv=resolved_real_event_csv,
        label_scheme=resolved_label_scheme,
        train_ratio=resolved_train_ratio,
        validation_ratio=resolved_validation_ratio,
        test_ratio=resolved_test_ratio,
        purge_gap_minutes=resolved_purge_gap_minutes,
        split_strategy=resolved_split_strategy,
        total_real_row_count=None,
        source="explicit_cli_count",
    )
