from __future__ import annotations

import pandas as pd


def _evaluate_split_score(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    total_rows: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    abnormal_classes: list[str],
) -> float:
    val_counts = validation_df["context_label"].value_counts().to_dict()
    test_counts = test_df["context_label"].value_counts().to_dict()
    val_coverage = sum(val_counts.get(label, 0) > 0 for label in abnormal_classes)
    test_coverage = sum(test_counts.get(label, 0) > 0 for label in abnormal_classes)
    val_support = sum(min(val_counts.get(label, 0), 5) for label in abnormal_classes)
    test_support = sum(min(test_counts.get(label, 0), 5) for label in abnormal_classes)
    ratio_penalty = (
        abs(len(train_df) / total_rows - train_ratio)
        + abs(len(validation_df) / total_rows - validation_ratio)
        + abs(len(test_df) / total_rows - test_ratio)
    )
    return 200.0 * (val_coverage + test_coverage) + 10.0 * (val_support + test_support) - 100.0 * ratio_penalty


def _chronological_with_gap(
    ordered: pd.DataFrame,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    purge_gap_minutes: int,
) -> dict[str, pd.DataFrame]:
    total = len(ordered)
    train_end_index = max(int(total * train_ratio), 1)
    validation_end_index = max(int(total * (train_ratio + validation_ratio)), train_end_index + 1)
    validation_end_index = min(validation_end_index, total - 1)

    train_boundary_ts = int(ordered.iloc[train_end_index - 1]["timestamp"])
    validation_boundary_ts = int(ordered.iloc[validation_end_index - 1]["timestamp"])
    purge_gap_seconds = purge_gap_minutes * 60

    train_mask = ordered["timestamp"] <= train_boundary_ts
    validation_mask = (ordered["timestamp"] > train_boundary_ts + purge_gap_seconds) & (
        ordered["timestamp"] <= validation_boundary_ts
    )
    test_mask = ordered["timestamp"] > validation_boundary_ts + purge_gap_seconds

    train_df = ordered.loc[train_mask].copy()
    validation_df = ordered.loc[validation_mask].copy()
    test_df = ordered.loc[test_mask].copy()

    if validation_df.empty or test_df.empty:
        raw_train = ordered.iloc[:train_end_index].copy()
        raw_validation = ordered.iloc[train_end_index:validation_end_index].copy()
        raw_test = ordered.iloc[validation_end_index:].copy()
        train_df = raw_train
        validation_df = raw_validation
        test_df = raw_test
    return {
        "train": train_df.reset_index(drop=True),
        "validation": validation_df.reset_index(drop=True),
        "test": test_df.reset_index(drop=True),
    }


def _coverage_aware_temporal(
    ordered: pd.DataFrame,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    purge_gap_minutes: int,
) -> dict[str, pd.DataFrame]:
    total = len(ordered)
    purge_gap_seconds = purge_gap_minutes * 60
    target_train_end = int(total * train_ratio)
    target_validation_end = int(total * (train_ratio + validation_ratio))
    train_low = max(int(total * 0.55), target_train_end - int(total * 0.12))
    train_high = min(int(total * 0.80), target_train_end + int(total * 0.12))
    validation_low = max(target_validation_end - int(total * 0.10), train_low + 50)
    validation_high = min(int(total * 0.95), target_validation_end + int(total * 0.10))
    abnormal_classes = [label for label in sorted(ordered["context_label"].unique()) if label != "normal_context"]
    best: tuple[float, dict[str, pd.DataFrame]] | None = None

    for train_end in range(train_low, train_high + 1, 25):
        train_boundary_ts = int(ordered.iloc[train_end - 1]["timestamp"])
        for validation_end in range(max(train_end + 50, validation_low), validation_high + 1, 25):
            validation_boundary_ts = int(ordered.iloc[validation_end - 1]["timestamp"])
            train_df = ordered.loc[ordered["timestamp"] <= train_boundary_ts].copy()
            validation_df = ordered.loc[
                (ordered["timestamp"] > train_boundary_ts + purge_gap_seconds)
                & (ordered["timestamp"] <= validation_boundary_ts)
            ].copy()
            test_df = ordered.loc[ordered["timestamp"] > validation_boundary_ts + purge_gap_seconds].copy()
            if len(validation_df) < 200 or len(test_df) < 200:
                continue
            score = _evaluate_split_score(
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
                total_rows=total,
                train_ratio=train_ratio,
                validation_ratio=validation_ratio,
                test_ratio=test_ratio,
                abnormal_classes=abnormal_classes,
            )
            candidate = {
                "train": train_df.reset_index(drop=True),
                "validation": validation_df.reset_index(drop=True),
                "test": test_df.reset_index(drop=True),
            }
            if best is None or score > best[0]:
                best = (score, candidate)

    if best is None:
        return _chronological_with_gap(
            ordered=ordered,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            purge_gap_minutes=purge_gap_minutes,
        )
    return best[1]


def split_real_dataset(
    real_df: pd.DataFrame,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    purge_gap_minutes: int,
    split_strategy: str = "coverage_aware_temporal",
) -> dict[str, pd.DataFrame]:
    ordered = real_df.sort_values("timestamp").reset_index(drop=True).copy()
    total = len(ordered)
    if total < 10:
        raise ValueError("Real dataset is too small for chronological splitting.")
    if split_strategy == "coverage_aware_temporal":
        splits = _coverage_aware_temporal(
            ordered=ordered,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            purge_gap_minutes=purge_gap_minutes,
        )
    else:
        splits = _chronological_with_gap(
            ordered=ordered,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            purge_gap_minutes=purge_gap_minutes,
        )
    train_df = splits["train"].copy()
    validation_df = splits["validation"].copy()
    test_df = splits["test"].copy()
    train_df["split_name"] = "train"
    validation_df["split_name"] = "validation"
    test_df["split_name"] = "test"

    return {
        "train": train_df.reset_index(drop=True),
        "validation": validation_df.reset_index(drop=True),
        "test": test_df.reset_index(drop=True),
    }
