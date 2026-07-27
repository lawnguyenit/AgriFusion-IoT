from __future__ import annotations

from sklearn import __version__ as sklearn_version
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression

from Backend.Benchmark.model_suite.contracts.model_adapter import ModelProfile


def build_dummy_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    kwargs = dict(profile.hyperparameters)
    return DummyClassifier(**kwargs), sklearn_version


def build_logistic_regression_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    kwargs = dict(profile.hyperparameters)
    kwargs.setdefault("random_state", random_seed)
    return LogisticRegression(**kwargs), sklearn_version


def build_extra_trees_classifier(
    profile: ModelProfile,
    random_seed: int,
    thread_count: int,
    class_count: int,
) -> tuple[object, str]:
    kwargs = dict(profile.hyperparameters)
    kwargs.setdefault("random_state", random_seed)
    kwargs.setdefault("n_jobs", thread_count)
    return ExtraTreesClassifier(**kwargs), sklearn_version
