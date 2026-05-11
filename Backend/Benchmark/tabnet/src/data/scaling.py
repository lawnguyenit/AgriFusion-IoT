from __future__ import annotations

from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.tabnet.src.data.contracts import PreparedDataset, ScaledSplitData


def scale_dataset_splits(prepared_dataset: PreparedDataset) -> ScaledSplitData:
    dataframe = prepared_dataset.dataframe
    feature_columns = prepared_dataset.feature_columns
    split_slices = prepared_dataset.split_slices

    train_frame = dataframe.iloc[split_slices["train"]]
    validation_frame = dataframe.iloc[split_slices["validation"]]
    test_frame = dataframe.iloc[split_slices["test"]]

    scaler = StandardScaler()
    train_features = scaler.fit_transform(train_frame[feature_columns])
    validation_features = scaler.transform(validation_frame[feature_columns])
    test_features = scaler.transform(test_frame[feature_columns])

    return ScaledSplitData(
        train_features=train_features,
        validation_features=validation_features,
        test_features=test_features,
        scaler=scaler,
    )
