# External q/τ label candidates

This lane builds auditable weak-label candidates from registered source
measurements. It does not mutate intake/feature outputs, select a primary
candidate, build train/test splits, or fit models.

## Frozen candidate policy

- Fit empirical linear quantiles using only the first 21 days from the
  canonical source's first timestamp.
- Sweep event-tail shares q = 5%, 10%, 15%, and 20%, and semantic persistence
  durations τ = 30, 45, 60, and 90 minutes. Every q/τ pair remains a
  sensitivity candidate; no primary label is selected.
- Stuard uses the lower tail of `soil_moisture_pct`. UCI has independent
  upper-tail heads for `sensor.co` and `sensor.nox`; q denotes exceedance share,
  so thresholds are fit at quantile `1-q` for those heads.
- Convert τ to `K_e(τ)=ceil(τ / median_cadence_e)`. Tail anchors become positive
  when the current tail run reaches K observations. Strict continuity follows
  the in-house 13–17 minute bounds normalized by its 15-minute nominal cadence.
- A valid current value outside its candidate tail is negative. Missing values
  and tail values whose run has not reached K remain unknown. UCI joint `REF`
  is emitted only when both CO and NOx labels are known negative; each head is
  retained independently, including when the other head is unknown.
- Analyzer criteria and post-hoc water-meter evidence are never loaded into
  the label engine.

## Outputs

Each run is source-bound under a new folder and writes:

- `candidate_labels.parquet`: one row per `sample_id`, nullable binary target
  columns, per-candidate status columns, and joint label states;
- `candidate_registry.csv`: threshold fit values, q/τ definition, target role,
  and corresponding column names;
- `entity_persistence_registry.csv`: measured cadence and realized K per τ and
  source entity;
- `candidate_support_audit.csv`: positive/negative/unknown support over the
  full source, calibration interval, and post-calibration interval;
- run manifest, readable report, and artifact hashes.

The label table is joined to the feature superset only by `sample_id`; select
specific binary target columns and a split artifact when invoking the generic
pre-train audit. Review the support audit before choosing a primary candidate.

```powershell
python -m Backend.Benchmark.external_labels.main `
  --canonical <intake-run>/canonical.parquet `
  --intake-manifest <intake-run>/run_manifest.json `
  --output-root Backend/Output_data/wade_external_validation_pack/processed/labels
```

The calibration window and candidate grid can be overridden explicitly with
CLI flags; each run records the effective policy. Such overrides create a new
candidate run and do not alter earlier outputs.
