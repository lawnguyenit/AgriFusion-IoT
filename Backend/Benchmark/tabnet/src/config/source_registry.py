from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkSourceProfile:
    name: str
    description: str
    default_csv: Path | None


def build_source_registry(root_dir: Path) -> dict[str, BenchmarkSourceProfile]:
    fuzzy_root = root_dir / "Backend" / "Benchmark" / "fuzzy_logic_basic"
    return {
        "layer1": BenchmarkSourceProfile(
            name="layer1",
            description="Current aligned CSV built from fuzzy Layer1 output.",
            default_csv=fuzzy_root / "dataset" / "flb_input_aligned.csv",
        ),
        "layer2": BenchmarkSourceProfile(
            name="layer2",
            description="Reserved for future fuzzy Layer2 benchmark exports.",
            default_csv=None,
        ),
        "layer3": BenchmarkSourceProfile(
            name="layer3",
            description="Reserved for future fuzzy Layer3 benchmark exports.",
            default_csv=None,
        ),
        "layer4": BenchmarkSourceProfile(
            name="layer4",
            description="Reserved for future fuzzy Layer4 benchmark exports.",
            default_csv=None,
        ),
        "layer5": BenchmarkSourceProfile(
            name="layer5",
            description="Reserved for future fuzzy Layer5 benchmark exports.",
            default_csv=None,
        ),
        "custom": BenchmarkSourceProfile(
            name="custom",
            description="Explicit CSV path passed from the CLI.",
            default_csv=None,
        ),
    }


def resolve_source_csv(
    *,
    source_kind: str,
    input_csv: Path | None,
    root_dir: Path,
) -> tuple[str, Path]:
    registry = build_source_registry(root_dir)
    if source_kind not in registry:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown source kind '{source_kind}'. Available: {available}")

    profile = registry[source_kind]
    if input_csv is not None:
        return source_kind, input_csv.resolve()

    if profile.default_csv is None:
        raise FileNotFoundError(
            f"Source kind '{source_kind}' is reserved for future fuzzy outputs. "
            "Pass --input-csv with the generated CSV when it exists."
        )

    return source_kind, profile.default_csv.resolve()
