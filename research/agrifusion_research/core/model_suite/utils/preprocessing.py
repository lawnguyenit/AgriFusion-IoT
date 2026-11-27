from __future__ import annotations

import hashlib
import json

import numpy as np
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


def hash_sample_ids(sample_ids: list[str]) -> str:
    payload = json.dumps(sample_ids, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fit_preprocessing_bundle(
    *,
    train_features: np.ndarray,
    evaluation_features: dict[str, np.ndarray],
    feature_names: list[str],
    enable_scaling: bool,
    enable_variance_threshold: bool,
) -> dict[str, object]:
    imputer = SimpleImputer(strategy="median")
    train_imputed = imputer.fit_transform(train_features)
    evaluation_imputed = {
        partition_name: imputer.transform(features)
        for partition_name, features in evaluation_features.items()
    }

    scaler = StandardScaler() if enable_scaling else None
    if scaler is not None:
        train_scaled = scaler.fit_transform(train_imputed)
        evaluation_scaled = {
            partition_name: scaler.transform(features)
            for partition_name, features in evaluation_imputed.items()
        }
    else:
        train_scaled = train_imputed
        evaluation_scaled = evaluation_imputed

    selector = VarianceThreshold() if enable_variance_threshold else None
    if selector is not None:
        train_selected = selector.fit_transform(train_scaled)
        evaluation_selected = {
            partition_name: selector.transform(features)
            for partition_name, features in evaluation_scaled.items()
        }
        selected_mask = selector.get_support()
    else:
        train_selected = train_scaled
        evaluation_selected = evaluation_scaled
        selected_mask = np.ones(len(feature_names), dtype=bool)

    selected_feature_names = [
        feature_name
        for feature_name, keep in zip(feature_names, selected_mask, strict=True)
        if keep
    ]
    return {
        "imputer": imputer,
        "scaler": scaler,
        "selector": selector,
        "train_features": train_selected,
        "evaluation_features": evaluation_selected,
        "selected_feature_names": selected_feature_names,
    }
