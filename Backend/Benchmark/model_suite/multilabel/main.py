from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import MultiLabelRunConfig
from .runner import run_independent_binary_heads


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit independent binary heads from a ready pre-train audit.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20260929)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--hyperparameters-json", type=Path)
    args = parser.parse_args()
    overrides = None
    if args.hyperparameters_json is not None:
        import json

        overrides = json.loads(args.hyperparameters_json.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict):
            raise ValueError("--hyperparameters-json must contain a JSON object.")
    result = run_independent_binary_heads(
        MultiLabelRunConfig(
            audit_dir=args.audit_dir,
            target_columns=tuple(args.targets),
            model_key=args.model,
            output_root=args.output_root,
            probability_threshold=args.threshold,
            random_seed=args.seed,
            thread_count=args.threads,
            hyperparameter_overrides=overrides,
        )
    )
    print(f"status={result.status}")
    print(f"run_id={result.run_id}")
    print(f"output_dir={result.output_dir}")


if __name__ == "__main__":
    main()
