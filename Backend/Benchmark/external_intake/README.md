# External dataset intake

`external_intake` preserves and adapts the two external WADE sources into
versioned, auditable canonical candidates. It does not create research
labels, model features, splits, or predictions.

## Supported inputs

- `stuard_tomato_irrigation_2023`: soil, environment, and water-meter CSV
  streams. Joins are backward as-of with an eight-minute tolerance. Matched
  timestamps and alignment ages are retained; future matches fail closed.
  Repeated source headers are audited as excluded rows; other missing or
  unknown line IDs fail validation instead of pooling records.
- `uci_air_quality_360`: the official UCI ZIP or its extracted CSV. The `-200`
  sentinel is represented as missing. Analyzer `(GT)` fields are namespaced as
  `criterion.*` and the sensor/context fields as `sensor.*` or `context.*`.
  Intake records the criterion columns that downstream feature builders must
  exclude.

## Storage

Raw releases are copied byte-for-byte or downloaded explicitly under
`Backend/Output_data/wade_external_validation_pack/raw/<dataset_id>/<release_id>/`.
Each release has a `raw_manifest.json` with source URLs, checksums, and sizes.
Processing runs are isolated under
`Backend/Output_data/wade_external_validation_pack/processed/<dataset_id>/<run_id>/`
and include a typed canonical Parquet file, audit manifest, report, and artifact
catalog. Existing raw releases are never overwritten; choose a new `release_id`
for another source snapshot.

The current pack has full UCI and Stuard releases and full-data intake/feature
runs. UCI has 9,357 valid timestamped rows plus 114 audited blank source rows;
the observed last timestamp is later than the date range in the published
description, so resolve that discrepancy before chronological split design.
Label generation and temporal split publication remain separate and require
frozen source-specific rules. Dataset DOI, license, citation, and use limits
are copied into the source metadata in each run manifest.

## Commands

Process already downloaded files without network access:

```powershell
python -m Backend.Benchmark.external_intake.main --dataset stuard_tomato_irrigation_2023 --input-dir <folder-with-three-csv-files> --release-id stuard-2023-v1
python -m Backend.Benchmark.external_intake.main --dataset uci_air_quality_360 --input-dir <folder-with-air+quality.zip> --release-id uci-360-v1
```

Download a new raw release explicitly:

```powershell
python -m Backend.Benchmark.external_intake.main --dataset uci_air_quality_360 --download
```

Read [FLOW.md](FLOW.md) for the implemented responsibilities and handoff.
The source-aware value/window feature stage is documented in
[`../external_features/README.md`](../external_features/README.md).
