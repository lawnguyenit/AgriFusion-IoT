from __future__ import annotations

import argparse
from pathlib import Path

from .stuard_controls import StuardControlConfig, run_stuard_control_arms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed-split Stuard prior and line-plus-sensor controls.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--sensor-predictions", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model", default="xgboost")
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    output = run_stuard_control_arms(StuardControlConfig(
        audit_dir=args.audit_dir,
        target_column=args.target,
        sensor_predictions_path=args.sensor_predictions,
        output_root=args.output_root,
        model_key=args.model,
        random_seed=args.seed,
        thread_count=args.threads,
    ))
    print(output.resolve())


if __name__ == "__main__":
    main()
