from __future__ import annotations


def build_split_slices(row_count: int, train_ratio: float, validation_ratio: float) -> dict[str, slice]:
    if row_count < 3:
        raise ValueError("Need at least 3 cleaned rows to create train/validation/test splits.")

    train_end = int(row_count * train_ratio)
    validation_end = train_end + int(row_count * validation_ratio)

    train_end = max(1, min(train_end, row_count - 2))
    validation_end = max(train_end + 1, min(validation_end, row_count - 1))

    return {
        "train": slice(0, train_end),
        "validation": slice(train_end, validation_end),
        "test": slice(validation_end, row_count),
    }
