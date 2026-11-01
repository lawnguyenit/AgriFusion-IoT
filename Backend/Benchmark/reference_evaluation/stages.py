"""Source audit, fitting and R0 case orchestration; numerical logic is separate."""
import json
import time
import joblib
import numpy as np
import pandas as pd
from . import audit, fitting
from .contracts import MODELS, FailedSupport
from .decisions import selection_rules
from .evaluation import compare_pool, save_inputs
from .preparation import prepare_frame, segments_from_frame
from .sources import acquire_source, read_source


def audit_source(store, source, download=False):
    sid = source["dataset_id"]
    archive = store.config.get("runtime", {}).get("local_archives", {}).get(sid)
    raw, manifest = acquire_source(source, store.root, download, archive)
    with store.unit("audit", sid, parents=(raw, manifest)) as run:
        if not run.reused:
            frame, adapter = read_source(source, raw)
            frame.to_csv(run.path / "canonical_before_audit.csv", index=False)
            frame, segments, support, metadata = prepare_frame(frame, store.config)
            frame.to_csv(run.path / "canonical.csv", index=False)
            frame[["sample_id", "entity", "timestamp", "partition", "segment_id", "score"]].to_csv(
                run.path / "split_assignments.csv", index=False)
            excluded = frame.loc[~frame.score].copy()
            excluded["exclusion_reason"] = np.where(excluded.F < 0, "REAL_REFERENCE_MISSING", "WARMUP_OR_SHORT_SEGMENT")
            excluded.to_csv(run.path / "excluded_rows.csv", index=False)
            run.csv("support_audit.csv", support)
            run.json("source_inventory.json", {"source": source, "adapter": adapter, "raw_manifest_path": str(manifest)})
            run.json("reference_manifest.json", metadata)
            run.json("dependency_audit.json", {"raw_dependency_count": metadata["raw_dependency_count"],
                                               "raw_dependencies_cross_partitions": False,
                                               "feature_history_resets_at_partition_and_segment": True})
            run.accept(["canonical.csv", "split_assignments.csv", "support_audit.csv", "reference_manifest.json"],
                       {"canonical_rows": len(frame), "eligible_segments": len(segments), **metadata},
                       f"# Source audit: {sid}\n\nRecorded rows: {len(frame)}; eligible segments: {len(segments)}.\n"
                       f"Hard gate passed: {metadata['hard_gate_passed']}. Support: {metadata['scientific_support_status']}.\n"
                       "See support_audit.csv and reference_manifest.json. No model fitted by this stage.",
                       metadata["scientific_support_status"])
    return run.path


def load_prepared(audit_dir):
    frame = pd.read_csv(audit_dir / "canonical.csv", dtype={"sample_id": str, "entity": str,
                                                          "partition": str, "segment_id": str})
    return segments_from_frame(frame), json.loads((audit_dir / "reference_manifest.json").read_text())


def fit_source(store, source_id, seed, audit_dir, segments, metadata):
    with store.unit("fit", f"{source_id}__{seed}", parents=(audit_dir / "READY.json",)) as run:
        if not run.reused:
            if not metadata["hard_gate_passed"]:
                run.manifest["scientific_support_status"] = "failed_support"
                raise FailedSupport(str(metadata["hard_gate_failures"]))
            bundle = fitting.fit_candidates(segments, store.config, source_id, seed)
            development = [s for s in segments if s.partition == "development"]
            policy = store.config["training"]["development_default"]["input_mask"]
            mask_seed = store.config["training"]["development_default"]["seed"]
            inputs, masks = fitting.make_inputs(development, bundle, store.config, source_id, policy, mask_seed)
            risks, _ = audit.true_risks(inputs, development, store.config["time_grid_and_target"]["K"])
            winner = min(risks, key=lambda r: (r["true_brier_audit"], MODELS.index(r["model"])))
            bundle["development_default"] = winner["model"]
            bundle["fit_signature"] = run.signature
            joblib.dump(bundle, run.path / "models.joblib")
            run.csv("development_risks.csv", risks); run.csv("development_masks.csv", masks)
            run.json("fit_metadata.json", {**bundle["fit_metadata"], "median": bundle["median"],
                                           "scale": bundle["scale"], "transition": bundle["transition"].tolist(),
                                           "prior": bundle["prior"].tolist(), "development_default": winner["model"]})
            run.accept(["models.joblib", "fit_metadata.json", "development_risks.csv"], bundle["fit_metadata"],
                       f"# Fit {source_id}, training-mask seed {seed}\n\nSix fixed candidates, four supervised fits "
                       f"(three HGB, one logistic), one Markov estimation and a constant. Development-only default: {winner['model']}.\n"
                       "Hyperparameters are fixed; no selection/assessment truth used for fit/default.",
                       metadata["scientific_support_status"])
    return run.path


def evaluate_case(store, source_id, seed, policy, mask_seed, audit_dir, fit_dir, segments, metadata):
    key = f"{source_id}__{seed}__{policy}__{mask_seed}"
    with store.unit("evaluate", key, parents=(audit_dir / "READY.json", fit_dir / "READY.json")) as run:
        if not run.reused:
            bundle = joblib.load(fit_dir / "models.joblib")
            base = {"dataset_id": source_id, "training_mask_seed": seed, "policy": policy, "mask_seed": mask_seed}
            pairs = []; points = []; risks = []; masks = []; checks = []; details = {}
            for partition in ("selection", "assessment"):
                reference = [s for s in segments if s.partition == partition]
                inputs, mask_rows = fitting.make_inputs(reference, bundle, store.config, source_id, policy, mask_seed)
                save_inputs(run.path / (partition + "_inputs.npz"), inputs)
                t = time.perf_counter()
                pair_rows, point_rows, info = compare_pool(inputs, bundle["transition"], bundle["prior"],
                    bundle["state_prevalence"], store.config["time_grid_and_target"]["K"],
                    store.config["comparison"]["numerical_tolerance"])
                info["all_R0_methods_wall_seconds"] = time.perf_counter()-t
                # Choices are fixed before any full-reference audit is joined.
                if partition == "selection":
                    choices = selection_rules(pair_rows, point_rows, bundle["development_default"],
                                              store.config["comparison"]["numerical_tolerance"])
                    run.json("selection_decisions.json", choices)
                truth_risks, labels = audit.true_risks(inputs, reference, store.config["time_grid_and_target"]["K"])
                audit_dir_out = run.path / "audit_only"; audit_dir_out.mkdir(exist_ok=True)
                np.savez_compressed(audit_dir_out / (partition + "_truth.npz"),
                                    END=np.concatenate(labels), F=np.concatenate([s.states for s in reference]),
                                    keys=np.concatenate([s.keys for s in reference]).astype(str))
                context = {**base, "partition": partition}
                pairs.extend({**context, **r} for r in pair_rows)
                points.extend({**context, **r} for r in point_rows)
                risks.extend({**context, **r} for r in truth_risks)
                masks.extend({**base, **r} for r in mask_rows)
                checks.extend({**context, **r} for r in audit.check_certificates(pair_rows, truth_risks))
                details[partition] = info
                if policy == "full_control" and any(abs(r["joint_upper"]-r["joint_lower"]) > 1e-9 for r in pair_rows):
                    raise AssertionError("Full-control R0 bounds did not collapse")
            selection_risks = [r for r in risks if r["partition"] == "selection"]
            assessment_risks = [r for r in risks if r["partition"] == "assessment"]
            outcomes = [{**base, **r} for r in audit.attach_decision_outcomes(choices, selection_risks, assessment_risks)]
            run.csv("pair_bounds.csv", pairs); run.csv("point_estimates.csv", points)
            run.csv("model_risks.csv", risks); run.csv("selection_results.csv", outcomes)
            run.csv("mask_summary.csv", masks); run.csv("certificate_checks.csv", checks)
            run.json("information_audit.json", {"evaluator_input_type": "EvaluationSegment", "truth_in_evaluator": False,
                                                "MNAR_propensity_given_to_evaluator": False, "partitions": details})
            run.json("case_identity.json", base)
            run.accept(["pair_bounds.csv", "selection_results.csv", "selection_inputs.npz", "assessment_inputs.npz"],
                       {"pair_comparisons": len(pairs), "selection_rules": len(outcomes), "information": details},
                       f"# R0 evaluation: {key}\n\n{len(pairs)} pair comparisons, {len(outcomes)} selection rules.\n"
                       "Selection decisions were recorded before truth joining. Assessment is a separate later outcome.\n"
                       "Fixed-model baselines and inconclusive verdicts are retained; inspect selection_results.csv.",
                       metadata["scientific_support_status"])
    return run.path
