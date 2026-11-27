# experiments: one-off studies and frozen phases

Code that answers one research question or records one decision. Nothing in `core/` or
`external/` may import from here (architecture test). Run with
`python -m agrifusion_research experiment <name> [<study>] ...`.

Every experiment has an `inputs.yaml`: the artifact runs it reads (paths relative to the repo
root), or an empty `inputs: {}` with a note when it reads none / takes them only as flags.
Pass it with `--inputs experiments/<name>/inputs.yaml`; command-line paths override it, and a
missing input stops the command (no hard-coded fallback).

| Name | Studies | Was (before GD5) |
|------|---------|------------------|
| `k_window_variants` | main, ordered, robustness, embedding, semantic, configured, rq1, rq1_program, rq1_review_controls | `model_suite/analysis/k_window_variants` |
| `wade_calibration` | main | `model_suite/analysis/wade_calibration` |
| `posthoc_model_analysis` | main | `model_suite/analysis/*.py` |
| `stuard_controls` | controls, acquisition | `model_suite/multilabel/stuard_*` |
| `paper_tables` | main | `model_suite/reporting/paper_tables*` |
| `weak_labels_phases` | phase_a, phase_b, phase_b_boundary, semantic_draft | `weak_labels/lifecycle/phase_a_readiness`, `phase_b_contract`, `architecture/tools` |
| `temporary_robustness_probe` | main | `temporary_robustness_probe` |
| `source_intake` | main | `source_intake` |

`weak_labels_phases`: Phase A (readiness) and Phase B (semantic contract) are frozen decision
steps. The native engine in `core/weak_labels/lifecycle/phase_c_native` reads their outputs as
files and does not import them (checked in GD5). Their reports are in
`docs/archive/weak_labels_phases/`.

Outputs of most studies still go to `output/research/model_suite/artifacts/` (their historical
location); the probe writes to `output/research/experiments/temporary_robustness_probe/`.
