# core: the benchmark pipeline

Code that runs, in this order, to go from canonical Layer1 telemetry to trained models.
Nothing here imports `external/` or `experiments/`.

| Package | Role | CLI stage | Output root |
|---------|------|-----------|-------------|
| `common/` | paths, hashes (`digests`), artifact writers, run-input YAML loader, provenance | - | - |
| `protocol_registry/` | E1/E2/E3 environments, stage authorities, 7d/5d fold policy | `protocol-registry` | `output/research/protocol_registry/` |
| `dataset_views/` | feature views X and the row-identified superset | `dataset-views` | `output/research/dataset_views/` |
| `weak_labels/` | native weak-label engine (phase C) and label release; audit-only analyses | `weak-labels`, `weak-labels-analysis` | `output/research/weak_labels/` |
| `evaluation_protocols/` | folds, cohorts, frozen runner contract, `validation_status` | `evaluation-protocols`, `e1e2-split-audit` | `output/research/evaluation_protocols/` |
| `gates/validity_lifecycle/` | re-audit of the locked sample universe | `validity-lifecycle` | `output/research/validity_lifecycle/` |
| `gates/pretrain_audit/` | explicit feature-group selection and X/y/split key checks | `pretrain-audit` | caller-given |
| `model_suite/` | training, metrics, plots, persistence; training gate; multilabel runner | `model`, `model-smoke`, `model-full`, `multilabel` | `output/research/model_suite/` |

Import direction inside core (allow-list in `Backend/tests/architecture/allowed_import_edges.txt`):
`common` is a leaf (of agrifusion it imports only `settings`); `protocol_registry` and
`dataset_views` import only `common` (plus `agrifusion`); `weak_labels` imports `common` and
`protocol_registry`; `evaluation_protocols` adds `dataset_views` and `weak_labels`;
`model_suite` imports `common` and `evaluation_protocols` (never the reverse) and reads the
gate file instead of importing a gate; `gates` read the outputs of all earlier stages.

`BENCHMARK_TO_MODEL_SUITE_SPEC.md` describes the runner-contract files that `model_suite` reads.
Each package keeps its own `README.md` / `FLOW.md`.
