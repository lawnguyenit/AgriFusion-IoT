"""Run inputs: the one config style for "which artifact runs does this command read".

Format (YAML, validated into ``RunInputs``)::

    description: free text (optional)
    inputs:
      snapshot_run_dir: output/research/dataset_views/artifacts/<run id>
      protocol_run_dir: /absolute/paths/work/too

Keys are argparse ``dest`` names. Relative paths resolve against the repository root.
Commands never fall back to a hard-coded run: every required input comes from the command
line or from an ``--inputs`` file, otherwise the command stops and names what is missing.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import REPO_ROOT

_ALLOWED_TOP_LEVEL = {"description", "inputs"}


@dataclass(frozen=True)
class RunInputs:
    source: Path
    description: str = ""
    paths: Mapping[str, Path] = field(default_factory=dict)

    def require(self, keys: Sequence[str]) -> dict[str, Path]:
        missing = [key for key in keys if key not in self.paths]
        if missing:
            raise ValueError(f"{self.source}: missing inputs {missing}")
        return {key: self.paths[key] for key in keys}


def load_run_inputs(path: Path, *, base_dir: Path = REPO_ROOT) -> RunInputs:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    unknown = sorted(set(payload) - _ALLOWED_TOP_LEVEL)
    if unknown:
        raise ValueError(f"{path}: unknown top-level keys {unknown}; allowed: {sorted(_ALLOWED_TOP_LEVEL)}")
    raw_inputs = payload.get("inputs") or {}
    if not isinstance(raw_inputs, dict):
        raise ValueError(f"{path}: 'inputs' must be a mapping of name -> path")
    paths: dict[str, Path] = {}
    for key, value in raw_inputs.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise ValueError(f"{path}: input name {key!r} is not a valid identifier")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}: input {key!r} must be a non-empty path string")
        candidate = Path(value)
        paths[key] = candidate if candidate.is_absolute() else (base_dir / candidate)
    return RunInputs(source=Path(path), description=str(payload.get("description") or ""), paths=paths)


def add_run_inputs_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--inputs",
        type=Path,
        default=None,
        help="YAML run-inputs file (see core/common/run_inputs.py); command-line paths override it.",
    )


def parse_with_run_inputs(
    parser: argparse.ArgumentParser,
    keys: Sequence[str],
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse ``argv``; fill each ``key`` left as None from ``--inputs``; fail if any is still unset."""
    if not any(action.dest == "inputs" for action in parser._actions):
        add_run_inputs_argument(parser)
    args = parser.parse_args(argv)
    if args.inputs is not None:
        run_inputs = load_run_inputs(args.inputs)
        for key in keys:
            if getattr(args, key, None) is None and key in run_inputs.paths:
                setattr(args, key, run_inputs.paths[key])
    missing = [key for key in keys if getattr(args, key, None) is None]
    if missing:
        flags = ", ".join("--" + key.replace("_", "-") for key in missing)
        parser.error(f"missing required inputs: {flags} (pass them or use --inputs <file.yaml>)")
    return args
