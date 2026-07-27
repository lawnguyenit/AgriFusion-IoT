from __future__ import annotations

from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS
from Backend.Benchmark.model_suite.contracts import ModelProfile


DEFAULT_ARTIFACT_ROOT: Path = BACKEND_PATHS.benchmark_dir / "model_suite" / "artifacts"

MODEL_CATALOG: dict[str, ModelProfile] = {
    "dummy_majority": ModelProfile(
        model_key="dummy_majority",
        display_name="Dummy Majority",
        family="baseline",
        library="scikit-learn",
        hyperparameters={"strategy": "prior"},
        enable_scaling=False,
        enable_variance_threshold=False,
        use_balanced_sample_weight=False,
    ),
    "logistic_regression": ModelProfile(
        model_key="logistic_regression",
        display_name="Logistic Regression",
        family="linear",
        library="scikit-learn",
        hyperparameters={
            "max_iter": 400,
            "solver": "lbfgs",
            "C": 1.0,
        },
        enable_scaling=True,
        enable_variance_threshold=True,
        use_balanced_sample_weight=True,
    ),
    "extra_trees": ModelProfile(
        model_key="extra_trees",
        display_name="Extra Trees",
        family="tree_ensemble",
        library="scikit-learn",
        hyperparameters={
            "n_estimators": 256,
            "max_depth": None,
            "min_samples_leaf": 1,
        },
        enable_scaling=False,
        enable_variance_threshold=False,
        use_balanced_sample_weight=True,
    ),
    "xgboost": ModelProfile(
        model_key="xgboost",
        display_name="XGBoost",
        family="boosted_tree",
        library="xgboost",
        hyperparameters={
            "n_estimators": 250,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "reg_lambda": 1.0,
        },
        enable_scaling=True,
        enable_variance_threshold=True,
        use_balanced_sample_weight=True,
    ),
    "realmlp": ModelProfile(
        model_key="realmlp",
        display_name="RealMLP",
        family="neural_mlp",
        library="pytabkit",
        hyperparameters={
            "n_epochs": 16,
            "batch_size": 256,
            "val_fraction": 0.2,
        },
        enable_scaling=True,
        enable_variance_threshold=False,
        use_balanced_sample_weight=False,
    ),
    "ft_transformer": ModelProfile(
        model_key="ft_transformer",
        display_name="FT-Transformer",
        family="tabular_transformer",
        library="pytabkit",
        hyperparameters={
            "max_epochs": 16,
            "batch_size": 256,
            "val_fraction": 0.2,
        },
        enable_scaling=True,
        enable_variance_threshold=False,
        use_balanced_sample_weight=False,
    ),
    "tabpfn": ModelProfile(
        model_key="tabpfn",
        display_name="TabPFN",
        family="foundation_tabular",
        library="tabpfn",
        hyperparameters={
            "n_estimators": 8,
            "fit_mode": "fit_preprocessors",
            "device": "auto",
        },
        enable_scaling=False,
        enable_variance_threshold=False,
        use_balanced_sample_weight=False,
    ),
}
