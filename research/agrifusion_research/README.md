# agrifusion_research

Research lane of AgriFusion-IoT: benchmark datasets, weak labels, evaluation protocols,
model training, and the one-off studies built on them. It reads the canonical Layer1 output
of the `agrifusion` package (`src/agrifusion`) and never writes into it.

Install from the repository root: `python -m pip install -e ".[research]"` (add `dev` for
tests). Import name: `agrifusion_research`.

## Layout: what each folder is for

| Folder | Contents | May import |
|--------|----------|------------|
| [`core/`](core/README.md) | the benchmark pipeline that runs in order (registry, X, y, protocol, gates, models) | `agrifusion`, `core` |
| [`external/`](external/README.md) | the parallel pipeline for public external datasets (Stuard, UCI) | `agrifusion`, `core`, `external` |
| [`experiments/`](experiments/README.md) | one-off studies and frozen decision phases; each has `inputs.yaml` | anything above |
| `cli.py` | the single command-line entry point | everything (dispatch only) |

Dependencies flow one way: `experiments -> external -> core -> agrifusion`. This is enforced
by `Backend/tests/test_architecture_import_graph.py` (no cycles, core never imports external
or experiments, external never imports experiments, `agrifusion` never imports this package).

## Running

```text
python -m agrifusion_research list                       # every command and its module
python -m agrifusion_research <stage> --help              # e.g. dataset-views, model
python -m agrifusion_research external <step> --help      # e.g. intake, labels
python -m agrifusion_research experiment <name> [<study>] --inputs experiments/<name>/inputs.yaml
```

`agrifusion-research` is the same CLI as a console script. Each command runs the existing
`main()` of its module, so `python -m agrifusion_research.core.dataset_views.main` still works.

Core stages, in run order: `protocol-registry`, `dataset-views`, `weak-labels`,
`evaluation-protocols`, gates (`validity-lifecycle`, `pretrain-audit`), then `model`
(`model-smoke`, `model-full`, `multilabel`).

## Where outputs go

Every lane writes under `output/research/<lane>/artifacts/<run_id>/` (gitignored), never next
to the code. Runs made before GD5 are under `Backend/Benchmark/<lane>/artifacts/`; move them to
the new location to use them with default paths or the recorded `inputs.yaml` files.

## Rules that the code enforces

- Training gate: `model`, `model-smoke`, `model-full` refuse a protocol run unless
  `run_metadata/protocol_validation_report.json` says `validation_status: ready`
  (`core/model_suite/gate.py`). `--allow-unaudited` overrides and is recorded in the run
  manifest. `multilabel` requires a pre-train audit with `ready_for_model_policy_review`.
- No hard-coded run ids: commands that read earlier runs take the paths as flags or from an
  `--inputs` YAML file (`core/common/run_inputs.py`); a missing input stops the command.
- One home for hashes: `core/common/digests.py` (two documented families; values pinned by tests).
- External datasets are declared once in `external/datasets.py`.

## Further reading

- [Backend/PIPELINE_FLOW.md](../../Backend/PIPELINE_FLOW.md): end-to-end flow and handoff files.
- [core/BENCHMARK_TO_MODEL_SUITE_SPEC.md](core/BENCHMARK_TO_MODEL_SUITE_SPEC.md): runner contract consumed by the model suite.
- Per-lane `README.md` (scope) and `FLOW.md` (control flow) inside each folder.
- Frozen weak-label phase notes: [docs/archive/weak_labels_phases](../../docs/archive/weak_labels_phases/README.md).
