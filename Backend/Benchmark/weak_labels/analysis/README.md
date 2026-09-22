# Weak-label audit analyses

This package contains derived, audit-only analyses over published native
weak-label releases. It does not replace label authority or mutate canonical
data.

## Temporal UNRES origin split

Build a traceable sibling artifact that separates the existing temporal UNRES
label into the two requested provenance origins:

```powershell
python Backend\Benchmark\weak_labels\analysis\main.py `
  --release-dir Backend\Benchmark\weak_labels\artifacts\phase_c\native_engine_20260805_045419_359073 `
  --protocol-run-dir Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260902_203645
```

The output directory is created beside the native Phase-C release under
`Backend/Benchmark/weak_labels/artifacts/phase_c/` with a name beginning
`temporal_unres_origin_split_`. It contains the derived row-level Parquet,
summary CSV, report, and a manifest with source hashes. No model training or
testing is performed by this command.
