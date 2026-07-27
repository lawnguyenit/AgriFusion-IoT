# Validity Lifecycle

`Backend/Benchmark/validity_lifecycle` is a standalone pre-training
audit lane. It reads an authoritative `evaluation_protocols` run and
re-expresses the benchmark sample universe as lifecycle-ready evidence
for E1, E2, and E3.

## Responsibilities

- lock explicit E1/E2/E3 environment boundaries;
- build a sample-level observation registry from canonical telemetry,
  weak labels, and dataset-view eligibility artifacts;
- audit class support, chronological split feasibility, eligibility
  loss, continuity issues, and matched-cohort integrity;
- quantify proxy-risk evidence such as EC-to-NPK determinism and pH
  stability before any new train run is allowed to proceed;
- publish an English report and machine-readable gate summary.

## Inputs

- one `evaluation_protocols` artifact run;
- linked canonical Layer1 history from that run manifest;
- linked `dataset_views` and `weak_labels` artifact runs referenced by
  the same protocol manifest.

## Outputs

Each lifecycle run writes:

- `run_metadata/`
- `configs/`
- `manifests/`
- `audits/`
- `reports/`
- `ambiguity/`
- `collection_repair/`

The primary report is `reports/validity_lifecycle_audit_report.md`.

## Non-Goals

- no model fitting;
- no new train/validation/test slicing inside this lane;
- no mutation of existing `evaluation_protocols` or `model_suite`
  contracts.

## Command

```powershell
python Backend/Benchmark/validity_lifecycle/main.py --evaluation-protocol-run-dir <protocol_run_dir>
```

If `--evaluation-protocol-run-dir` is omitted, the latest available
`evaluation_protocols` run is used.

## Flow

Read [FLOW.md](FLOW.md) for the implemented control flow.
