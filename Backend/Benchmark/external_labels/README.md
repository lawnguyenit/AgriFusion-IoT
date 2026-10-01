# External q/τ label candidates

This lane builds auditable weak-label candidates from registered source
measurements. It does not mutate intake/feature outputs, select a primary
candidate, build train/test splits, or fit models.

## Current candidate generator (reviewable candidates under approved source roles)

- Fit empirical linear quantiles using only the first 21 days from the
  canonical source's first timestamp.
- Sweep configured event-tail shares and persistence durations. Every q/τ pair
  remains a sensitivity candidate; no primary label is selected.
- Profiles remain dataset-specific. Stuard candidates use lower-tail soil
  moisture with per-line calibration cutoffs as primary and pooled cutoffs as
  sensitivity. UCI candidates use the certified analyzer fields
  `criterion.co_gt_mg_m3` and `criterion.nox_gt_ppb` as Y evidence. PT08 sensor
  responses are possible X fields, never the source for these pollutant labels.
- UCI PT08 fields are sensor responses nominally associated with gases, not
  criterion concentrations. A q-tail class is relative to the calibration
  distribution; it is not a regulatory or health threshold.
- UCI uses q=5/10/15/20% and τ=1/2/4 hours at its native hourly cadence. The
  urban event-duration literature motivates treating duration as a sensitivity
  axis; it does not establish a universal CO/NOx persistence cutoff. UCI q labels
  are relative high-concentration events, not regulatory exceedances.
- UCI converts τ to `K_e(τ)=ceil(τ / median_cadence_e)` and retains the existing
  strict cadence bounds. Stuard measures elapsed time from the current tail-run
  onset, with `g_max=2×entity median cadence` and no lower-gap bound. Its
  1.5×/3× continuity alternatives are support sensitivities only.
- A valid current value outside its candidate tail is negative. Every tail
  value below its persistence threshold is UNRES, whether the onset is observed
  or left-censored; a gap-interrupted run remains UNRES until its new history
  is sufficient. Missing target measurements remain unknown. UCI joint `REF`
  is emitted only when both CO and NOx labels are known negative; each head is
  retained independently, including when the other head is unknown.
- The label run reads only its configured target-source measurements. UCI
  criterion concentrations now define Y candidates and must stay out of X;
  Stuard water-meter evidence remains outside the soil-moisture label engine.
  All outputs remain sensitivity candidates pending support and semantic audit.

## Claim discovery and review

Before selecting label semantics, use
[`CLAIM_DISCOVERY.md`](CLAIM_DISCOVERY.md) to inventory what each dataset can
support, what is only a weak proxy, and what is unsupported with explicit
reasons. External knowledge informs hypotheses but does not create sample-level
ground truth. Unsupported or unselected claims are not `REF`; `REF` only means
known-negative for all selected heads under an approved rule. Semantic claims
remain human-authored. The executable `claim_discovery` step summarizes
canonical fields and source roles before labeling, but the reviewed claim-ID
gate is not yet enforced by the label generator.

Run the evidence inventory first:

```powershell
python -m Backend.Benchmark.claim_discovery.main `
  --canonical <intake-run>/canonical.parquet `
  --intake-manifest <intake-run>/run_manifest.json `
  --output-root Backend/Output_data/wade_external_validation_pack/processed/claim_discovery
```

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
CLI flags; each run records the effective policy. Stuard continuity sensitivity
runs can override the profile's maximum gap with
`--max-gap-cadence-fraction 1.5` or `3.0`; the approved primary remains 2.0.
Each override creates a new candidate run and does not alter earlier outputs.
