from __future__ import annotations

import argparse
from pathlib import Path

from .stuard_acquisition_controls import run_stuard_acquisition_controls


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate Stuard measurement-value gains from acquisition-pattern gains.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="xgboost")
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--bootstrap-repetitions", type=int, default=1000)
    args = parser.parse_args()
    output = run_stuard_acquisition_controls(
        audit_dir=args.audit_dir,
        target_column=args.target,
        output_dir=args.output_dir,
        model_key=args.model,
        random_seed=args.seed,
        thread_count=args.threads,
        bootstrap_repetitions=args.bootstrap_repetitions,
    )
    print(output.resolve())


if __name__ == "__main__":
    main()
