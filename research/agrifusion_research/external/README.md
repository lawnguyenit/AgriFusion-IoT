# external: public datasets beside the in-house pipeline

A second pipeline for public datasets (Stuard tomato irrigation 2023, UCI Air Quality 360).
It shares only `core.common` (hashes, artifact writers) and `core.gates.pretrain_audit`
consumes its outputs as files.

```text
intake -> features --\
       -> labels  ----+-> support_audit -> (core) pretrain-audit -> model multilabel
       -> splits  --/
claims: evidence inventory for human claim review (reads intake output)
```

| Step | CLI | Writes run ids |
|------|-----|----------------|
| `intake/` | `external intake --dataset <id>` | `external_intake_<dataset_id>_<UTC stamp>` |
| `features/` | `external features` | `external_features_<dataset_id>_<UTC stamp>` |
| `labels/` | `external labels` | `external_labels_<dataset_id>_<UTC stamp>` |
| `splits/` | `external splits` | see `splits/README.md` |
| `support_audit/` | `external support-continuity`, `support-refresh`, `support-grid` | see `support_audit/README.md` |
| `claims/` | `external claims` | see `claims/` |

Run-id prefixes are unchanged from the pre-GD5 lanes, so old artifact lineage stays readable.

`datasets.py` is the single registry: one `DatasetProfile` per dataset id with its source
files, metadata, intake adapter key, feature profile, label profile and the policy text written
into manifests. Lane code never compares against a dataset id (tested in
`Backend/tests/test_external_registry.py`). To add a dataset: add a `DatasetProfile` and, if
the raw format is new, an adapter in `intake/adapters/` registered in `ADAPTERS`.

Default data root: `output/wade_external_validation_pack/{raw,processed}`.
