"""Local P2 gates. Unit-only mode is CI evidence, not full protocol completion."""
from pathlib import Path
import json
import math
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import pandas as pd
from .storage import sha256

FIXTURE_FILES = ("partial_reference_pilot.py", "learning_gap_reference.py", "reference_sensitivity.py",
                 "generic_milp_check.py", "pilot_protocol.json", "sensitivity_protocol.json",
                 "generic_solver_protocol.json", "reusable_scores.npz", "next_study_protocol.json",
                 "Reproduce_partial_reference.md", "Reproduce_route_review.md", "group_outcome_B.npz",
                 "group_test_temporal.npz", "pair_bounds.csv", "selection_results.csv",
                 "summarize_partial_reference.py")


def validate_local(store, fixture_dir=None, unit_only=False):
    parents = []
    if not unit_only:
        if fixture_dir is None:
            raise FileNotFoundError("Full P2 needs the delivered Jena fixture; install it or pass --fixture-dir")
        fixture_dir = Path(fixture_dir).resolve()
        parents = [fixture_dir / name for name in FIXTURE_FILES]
        missing = [str(p) for p in parents if not p.is_file()]
        if missing:
            raise FileNotFoundError("Missing fixture inputs: " + ", ".join(missing))
    key = "unit_only" if unit_only else "unit_and_legacy_fixture"
    with store.unit("validate", key, parents=parents, extra={"unit_only": unit_only}) as run:
        if not run.reused:
            if not unit_only:
                expected=json.loads((Path(__file__).parent/'configs/legacy_fixture_hashes.json').read_text())
                for file in parents:
                    if sha256(file)!=expected[file.name]:
                        raise ValueError(f'Legacy fixture bytes changed: {file.name}; restore the delivered original')
            module = "Backend.Benchmark.reference_evaluation.tests"
            suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / "tests"),
                        pattern="test_*.py", top_level_dir=str(Path(__file__).resolve().parents[3]))
            with (patch('sklearn.ensemble.HistGradientBoostingClassifier.fit',
                       side_effect=AssertionError('Forecaster fits are forbidden in the correctness test suite')) as hgb,
                 patch('sklearn.linear_model.LogisticRegression.fit',
                       side_effect=AssertionError('Forecaster fits are forbidden in the correctness test suite')) as lr):
                result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
            record = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "skipped": len(result.skipped), "legacy_fixture_verified": False,
                      "real_source_model_fits_in_tests": 0, "full_P2_gate": False}
            record['HGB_fit_calls_in_tests']=hgb.call_count
            record['logistic_fit_calls_in_tests']=lr.call_count
            run.json("test_results.json", record)
            if not result.wasSuccessful():
                raise AssertionError("Focused local correctness suite failed")
            if not unit_only:
                dest = run.path / "legacy_fixture_work"; dest.mkdir()
                for path in parents:
                    shutil.copyfile(path, dest / path.name)
                for script in ("reference_sensitivity.py", "generic_milp_check.py"):
                    process = subprocess.run([sys.executable, str(dest/script)], text=True, encoding="utf-8",
                                             errors="replace", capture_output=True, timeout=300)
                    print(process.stdout, end=""); print(process.stderr, end="", file=sys.stderr)
                    if process.returncode != 0:
                        raise RuntimeError(f"Legacy no-refit check failed: {script}, exit {process.returncode}")
                data = pd.read_csv(dest / "reference_error_bounds.csv")
                counts = {r: int(data.loc[data.global_error_budget == r, "certified_EM"].astype(str).str.lower().eq("true").sum()) for r in range(4)}
                if counts != {0:5, 1:4, 2:1, 3:0}:
                    raise AssertionError(f"Legacy certificate regression differs: {counts}")
                solver = json.loads((dest / "generic_solver_summary.json").read_text())
                if not solver["all_optimal_values_match_DP"] or not solver["all_returned_witnesses_valid"]:
                    raise AssertionError("Legacy solver/witness regression failed")
                def finite(value):
                    if isinstance(value,float) and not math.isfinite(value):return None
                    if isinstance(value,dict):return {key:finite(v) for key,v in value.items()}
                    if isinstance(value,list):return [finite(v) for v in value]
                    return value
                record.update(legacy_fixture_verified=True, full_P2_gate=True, fixture_checksums_verified=True,
                              legacy_certificate_counts=counts, legacy_solver_summary=finite(solver),
                              legacy_nonfinite_summary_values_normalized_to_null=True,
                              original_legacy_summary_preserved=True)
                run.json("test_results.json", record)
            run.accept(["test_results.json"], record,
                       f"# Correctness validation\n\n{record['tests_run']} tests; failures={record['failures']}, errors={record['errors']}.\n"
                       f"Legacy fixture verified: {record['legacy_fixture_verified']}. Full P2 gate: {record['full_P2_gate']}.\n"
                       "No real-source forecaster was trained by the correctness suite; unit-only mode does not certify full P2.")
    return run.path
