from pathlib import Path

CONFIG_ROOT = Path(__file__).resolve().parent
ARTIFACT_POLICY_PATH = CONFIG_ROOT / "artifact_policy.yaml"
METRIC_PROFILES_PATH = CONFIG_ROOT / "metric_profiles.yaml"
MODEL_REGISTRY_PATH = CONFIG_ROOT / "model_registry.yaml"
SEED_POLICY_PATH = CONFIG_ROOT / "seed_policy.yaml"
TRAINING_PROFILES_PATH = CONFIG_ROOT / "training_profiles.yaml"

__all__ = [
    "ARTIFACT_POLICY_PATH",
    "CONFIG_ROOT",
    "METRIC_PROFILES_PATH",
    "MODEL_REGISTRY_PATH",
    "SEED_POLICY_PATH",
    "TRAINING_PROFILES_PATH",
]
