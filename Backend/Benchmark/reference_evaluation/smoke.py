"""P3 local fit smoke. Its toy results are never efficacy evidence."""
import numpy as np
from . import fitting, audit
from .contracts import Segment
from .evaluation import compare_pool, save_inputs
from .masking import mask_observations
from .features import causal_features


def toy_segments(warmup=24):
    rng = np.random.default_rng(20261101); output = []
    pattern = np.array([1, 1, 1, 1, 0, 0, 1, 0], dtype=np.int8)
    for partition in ("train", "development"):
        for number in range(2):
            states = np.roll(np.tile(pattern, 48), number)
            values = np.where(states, 1., -1.) + rng.normal(0, .03, len(states))
            sid = f"synthetic_smoke_{partition}_{number}"
            output.append(Segment(sid, "synthetic", partition,
                                  np.array([f"{sid}:{i}" for i in range(len(states))]),
                                  values, states, np.arange(len(states)) >= warmup))
    return output


def smoke_local(store, audit_paths=(), prepared=()):
    with store.unit("smoke", "synthetic_fit_and_recorded_prefix_checks",
                    parents=[p / "READY.json" for p in audit_paths]) as run:
        if not run.reused:
            segments = toy_segments(store.config["time_grid_and_target"]["warmup_per_segment"])
            bundle = fitting.fit_candidates(segments, store.config, "synthetic_smoke_not_efficacy", 11)
            development = [s for s in segments if s.partition == "development"]
            inputs, masks = fitting.make_inputs(development, bundle, store.config,
                                                "synthetic_smoke_not_efficacy", "mcar30", 11)
            rows, points, info = compare_pool(inputs, bundle["transition"], bundle["prior"], bundle["state_prevalence"],
                                             store.config["time_grid_and_target"]["K"])
            risks, _ = audit.true_risks(inputs, development, store.config["time_grid_and_target"]["K"])
            audit.check_certificates(rows, risks)
            save_inputs(run.path / "synthetic_smoke_inputs.npz", inputs)
            run.csv("synthetic_smoke_pairs.csv", rows)
            prefix_rows = []
            for source_id, source_segments in prepared:
                # Earliest train/development only; no assessment outcome inspected.
                for partition in ("train", "development"):
                    available = [s for s in source_segments if s.partition == partition][:2]
                    for s in available:
                        o, x, m, seed = mask_observations(s, "mcar30", store.config["study_id"], source_id,
                                                         11, 11, store.config["time_grid_and_target"]["warmup_per_segment"])
                        features = causal_features(x[:512], 24, bundle["median"], bundle["scale"])
                        if not np.isfinite(features).all():
                            raise AssertionError("Recorded early-prefix features are nonfinite")
                        prefix_rows.append({"dataset_id":source_id,"partition":partition,"segment_id":s.segment_id,
                                            "checked_prefix_rows":len(features),"role":"input/causality plumbing, no efficacy claim"})
            run.csv("recorded_prefix_checks.csv", prefix_rows,
                    None if prefix_rows else ["dataset_id","partition","segment_id","checked_prefix_rows","role"])
            run.accept(["synthetic_smoke_inputs.npz", "synthetic_smoke_pairs.csv", "recorded_prefix_checks.csv"],
                       {"toy_supervised_fits": 4, "toy_HGB_fits": 3, "recorded_prefix_checks":len(prefix_rows),
                        "real_source_fits":0,"comparison":info},
                       "# Local smoke\n\nFour supervised models fitted on synthetic train, evaluated on synthetic development.\n"
                       "Recorded early train/development prefixes were checked for plumbing only. "
                       "No selection/assessment-based tuning and no real-world efficacy conclusion follows.")
    return run.path
