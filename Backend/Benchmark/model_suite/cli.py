from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.contracts import ModelUnavailableError
from Backend.Benchmark.model_suite.config import ARTIFACT_POLICY_PATH
from Backend.Benchmark.model_suite.data import list_training_profiles
from Backend.Benchmark.model_suite.pipeline.orchestration import run_smoke_suite
from Backend.Benchmark.model_suite.registries import inspect_models_availability, list_model_profiles
from Backend.Benchmark.model_suite.config import TRAINING_PROFILES_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or inspect the benchmark model suite.")
    parser.add_argument("--list-models", action="store_true", help="Print the registered model catalog.")
    parser.add_argument("--list-profiles", action="store_true", help="Print the registered training profiles.")
    parser.add_argument(
        "--check-models",
        action="store_true",
        help="Check whether the requested model keys are available in the active Python environment.",
    )
    parser.add_argument(
        "--show-default-artifact-root",
        action="store_true",
        help="Print the default artifact root for standalone model_suite runs.",
    )
    parser.add_argument(
        "--smoke-protocol-run-dir",
        type=Path,
        default=None,
        help="Run the smoke model suite against an evaluation_protocols artifact run.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="smoke_phase1_protocol",
        help="Training profile name for smoke suite execution.",
    )
    parser.add_argument(
        "--model-keys",
        type=str,
        nargs="+",
        default=None,
        help="Optional explicit model keys to train instead of the default smoke_model_keys config.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable terminal progress UI and print only the final JSON summary.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    selected_model_keys = tuple(args.model_keys) if args.model_keys is not None else tuple(
        profile.model_key for profile in list_model_profiles()
    )
    if args.list_models:
        payload = [
            {
                "model_key": profile.model_key,
                "display_name": profile.display_name,
                "family": profile.family,
                "library": profile.library,
                "use_balanced_sample_weight": profile.use_balanced_sample_weight,
                "hyperparameters": profile.hyperparameters,
            }
            for profile in list_model_profiles()
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.list_profiles:
        print(json.dumps(list(list_training_profiles(TRAINING_PROFILES_PATH)), ensure_ascii=False, indent=2))
        return 0
    if args.show_default_artifact_root:
        payload = json.loads(ARTIFACT_POLICY_PATH.read_text(encoding="utf-8"))
        print(payload["artifact_root"])
        return 0
    if args.check_models:
        infos = inspect_models_availability(selected_model_keys)
        print(json.dumps(
            [
                {
                    "model_key": info.model_key,
                    "family": info.family,
                    "library": info.library,
                    "available": info.available,
                    "note": info.note,
                }
                for info in infos
            ],
            ensure_ascii=False,
            indent=2,
        ))
        return 0 if all(info.available for info in infos) else 2
    if args.smoke_protocol_run_dir is not None:
        try:
            result = run_smoke_suite(
                protocol_run_dir=args.smoke_protocol_run_dir.resolve(),
                profile_name=args.profile,
                model_keys=tuple(args.model_keys) if args.model_keys is not None else None,
                show_progress=not args.no_progress,
            )
        except ModelUnavailableError as exc:
            infos = inspect_models_availability(selected_model_keys)
            print(json.dumps(
                {
                    "status": "blocked",
                    "reason": "requested_models_unavailable",
                    "message": str(exc),
                    "model_availability": [
                        {
                            "model_key": info.model_key,
                            "family": info.family,
                            "library": info.library,
                            "available": info.available,
                            "note": info.note,
                        }
                        for info in infos
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ))
            return 2
        print(json.dumps(
            {
                "run_id": result.run_spec.run_id,
                "output_dir": str(result.run_spec.output_dir),
                "trained_jobs": int(result.summary["status"].astype("string").eq("trained").sum()) if not result.summary.empty else 0,
                "pooled_metric_groups": int(len(result.pooled_metrics)),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
