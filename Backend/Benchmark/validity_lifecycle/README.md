# Validity Lifecycle

`Backend/Benchmark/validity_lifecycle` is the tranche-0 audit and
synthesis lane. It reads an authoritative `evaluation_protocols` run,
links the corresponding `model_suite` outputs, and re-expresses the
benchmark sample universe as lifecycle-ready evidence for E1, E2, and
E3.

Governed runs also require the exact upstream `protocol_registry` linked by
the evaluation run. Local default environment specs remain only for historical
artifact/test compatibility and are not authority for new runs.

## Responsibilities

- lock explicit E1/E2/E3 environment boundaries;
- build a sample-level observation registry from canonical telemetry,
  weak labels, and dataset-view eligibility artifacts;
- audit class support, chronological split feasibility, eligibility
  loss, continuity issues, and matched-cohort integrity;
- quantify proxy-risk evidence such as EC-to-NPK determinism and pH
  stability before any new train run is allowed to proceed;
- consume preregistered claims, registered comparison pairs, and
  model-side prediction artifacts;
- emit dependency, estimability, source-expansion, and
  evidence-updated ambiguity artifacts under the tranche-0 contract;
- publish an English report and machine-readable gate summary.

## Inputs

- one `evaluation_protocols` artifact run;
- linked canonical Layer1 history from that run manifest;
- linked `dataset_views` and `weak_labels` artifact runs referenced by
  the same protocol manifest;
- one linked `model_suite` artifact run, resolved explicitly or by
  latest artifact timestamp.

## Outputs

Each lifecycle run writes:

- `run_metadata/`
- `configs/`
- `manifests/`
- `audits/`
- `reports/`
- `synthesis/`
- `ambiguity/`
- `collection_repair/`

Primary tranche-0 outputs include:

- `reports/validity_lifecycle_audit_report.md`
- `synthesis/dependency_effects.parquet`
- `synthesis/claim_evidence_matrix.csv`
- `ambiguity/evidence_updated_ambiguity_sets.yaml`

## Non-Goals

- no model fitting;
- no new train/validation/test slicing inside this lane;
- no mutation of existing `evaluation_protocols` or `model_suite`
  contracts;
- no automatic promotion from metric evidence to physical-causal claims.

## Command

```powershell
python Backend/Benchmark/validity_lifecycle/main.py --evaluation-protocol-run-dir <protocol_run_dir>
```

Add `--protocol-registry-run-dir <registry_run_dir>` for governed execution.
Phase A registries intentionally fail at the STOP gate.

If `--evaluation-protocol-run-dir` is omitted, the latest available
`evaluation_protocols` run is used. The implementation also resolves the
latest `model_suite` run unless a config-level override is supplied.

## Flow

Read [FLOW.md](FLOW.md) for the implemented control flow.
