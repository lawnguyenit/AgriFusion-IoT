# Benchmark Snapshot

## Purpose

This folder is the benchmark workspace for the AgriFusion-IoT backend.

It exists to keep:
- benchmark data preparation,
- embedding pretraining,
- downstream supervised experiments,
- and versioned schema evolution

separate from raw data collection and service code.

This file is the top-level snapshot for people who need to understand the current benchmark system quickly before reading module-specific code.

## Current Layout

- `fuzzy_logic_basic/`
  - benchmark data preparation and layer-by-layer CSV generation
- `pretrain_supervised/`
  - embedding pretraining and downstream supervised experiments
  - dataset profile reporting for Firebase size and label scarcity lives here under `reports/generate_data_profile_report.py`
- `direct_benchmark/`
  - direct downstream control-arm benchmark on raw v0-v5 features without embedding pretraining
  - includes a Word-friendly raw-feature profile report generator for tables, boxplots, and label composition charts

## Current Data Flow

### Flow A: Layer 1 baseline

`Backend/Output_data/Layer1`
-> `Backend/Benchmark/fuzzy_logic_basic/layer1`
-> `Backend/Benchmark/fuzzy_logic_basic/dataset/flb_input_aligned.csv`
-> `Backend/Benchmark/pretrain_supervised/pretrain`
-> embedding checkpoint/artifacts
-> `Backend/Benchmark/pretrain_supervised/v1`

### Flow B: Layer 2 ablations

`flb_input_aligned.csv`
-> `Backend/Benchmark/fuzzy_logic_basic/layer2`
-> `flb_l2_exp1.csv`
-> `flb_l2_exp2.csv`
-> `flb_l2_exp3.csv`
-> `flb_l2_exp4.csv`
-> `flb_l2_exp5.csv`
-> `flb_l2_exp6.csv`
-> `Backend/Benchmark/pretrain_supervised/pretrain` with `source_kind=layer2_exp1..exp5`
-> embedding checkpoint/artifacts
-> `Backend/Benchmark/pretrain_supervised/v2`

### Flow C: Layer 3 multi-window combos

`flb_input_aligned.csv`
-> `Backend/Benchmark/fuzzy_logic_basic/layer3_combo`
-> `flb_l3_combo1.csv`
-> `flb_l3_combo2.csv`
-> `flb_l3_combo3.csv`
-> `flb_l3_combo4.csv`
-> `Backend/Benchmark/pretrain_supervised/pretrain` with `source_kind=layer3_combo1..4`
-> embedding checkpoint/artifacts
-> `Backend/Benchmark/pretrain_supervised/v3`

### Flow D: Layer 2 full-set benchmark

`flb_l2_exp6.csv`
-> `Backend/Benchmark/pretrain_supervised/pretrain`
-> embedding checkpoint/artifacts
-> `Backend/Benchmark/pretrain_supervised/v4`

### Flow E: Direct raw-feature control arm

`flb_input_aligned.csv`
-> `Backend/Benchmark/direct_benchmark`
-> direct downstream model suite
-> control-arm metrics for `v0` and `v1`

## Version Contract

- `v1`
  - baseline downstream on embeddings generated from `layer1`
- `v2`
  - downstream on embeddings generated from `layer2_exp1..exp5`
- `v3`
  - downstream on embeddings generated from `layer3_combo1..layer3_combo4`
- `v4`
  - downstream on embeddings generated from `layer2_exp6`
- direct benchmark
  - downstream on raw benchmark features without embedding pretraining

The current version catalog is defined in:
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\version_catalog.py`

## Dataset Artifacts

Main benchmark artifacts currently expected under:
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset`

Important files:
- `flb_input_aligned.csv`
- `flb_input_with_events.csv`
- `flb_l2_exp1.csv`
- `flb_l2_exp2.csv`
- `flb_l2_exp3.csv`
- `flb_l2_exp4.csv`
- `flb_l2_exp5.csv`
- `flb_l2_exp6.csv`
- `flb_l3_combo1.csv`
- `flb_l3_combo2.csv`
- `flb_l3_combo3.csv`
- `flb_l3_combo4.csv`

## Label Source

Current downstream training does not invent labels from scratch.

It merges annotation columns from:
- `flb_input_with_events.csv`

Current binary label rule in downstream code:
- `big_label == "none"` -> `normal`
- `big_label != "none"` -> `abnormal`

Current ternary label rule groups:
- `weather_context`, `stress_context` -> `environmental_context`
- `system_timing`, `sensor_fault_anomaly`, `intervention_context` -> `operational_or_intervention`
- other non-`none` labels also fall into `operational_or_intervention`

This means current `abnormal` is a broad aggregate label, not a pure anomaly-only label.

The downstream label mapping lives in:
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v1\src\data\labels.py`

## Split Ownership

The current train/validation/test split is owned by the pretrain data pipeline.

Current behavior:
- sort rows by `timestamp`
- use a chronological split with an explicit purge gap between segments
- train: first 70 percent of the ordered rows before the purge gap
- validation: next 15 percent of the ordered rows after the first purge gap
- test: last 15 percent of the ordered rows after the second purge gap

Current split implementation:
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\src\data\splitting.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\src\data\preprocessing.py`

Downstream `v1`, `v2`, and `v4` reuse this split. They do not define an independent split policy.

## Current Strong Points

- `v1` provides a baseline on Layer 1 embeddings.
- `v2` supports explicit ablation experiments `exp1..exp5`.
- `v3` provides the multi-window combo benchmark on top of Layer2 features.
- `v4` consumes the `exp6` full-set export.
- pretrain and downstream outputs are separated per run and now grouped under date buckets such as `outputs/DD-MM-YYYY/<run_name>`.
- `v2` now supports backfilling optional models such as `xgboost` and `lightgbm` on existing run artifacts without rerunning the full suite.
- `pretrain_supervised/reports/generate_charts.py` can turn pretrain and downstream reports into PNG plots per run.
- `pretrain_supervised/reports/generate_data_profile_report.py` can produce the dataset size and abnormal-scarcity report pack from Firebase manifest, Layer1 manifest, and the labeled event CSV.

## Current Gaps

These are important and should be treated as open architecture debt:

1. Split-governance is now being extracted, but only `chronological_v1` is implemented today
   - stricter split regimes such as purge-gap or episode-aware split are still pending beyond the current gap-aware chronological split

2. Label provenance is not fully documented from source to `big_label`
   - downstream code clearly consumes `big_label`
   - but the exact producer path for `flb_input_with_events.csv` and `big_label` needs a cleaner trace in the benchmark tree

3. Some older fuzzy documentation is stale
   - for example, the fuzzy root README still references `layer15`
   - but the current visible tree under `fuzzy_logic_basic/` does not contain that folder

4. Evaluation policy is still not a separate first-class protocol document
   - split and label policy docs now exist, but promotion/evaluation rules are still not formalized

## Recommended Documentation Set

### Must-have

These should exist because they directly affect reproducibility:

1. `README.md` at the benchmark root
   - what the benchmark system is
   - which major subfolders exist
   - current version contract

2. one module README per processing folder
   - purpose
   - input
   - output
   - command
   - assumptions
   - limits

3. one split-policy document
   - who creates train/validation/test
   - how leakage is avoided
   - whether gaps, episode blocks, or temporal embargo are used

4. one label-policy document
   - where `normal` and `abnormal` come from
   - what `big_label` means
   - which labels are aggregated

### Good to have

These are optional but valuable when the system grows:

1. experiment registry
   - summary of `v1`, `v2_exp2`, `v2_exp5`, etc.

2. artifact registry
   - which CSV or checkpoint is the canonical output of each stage

3. evaluation protocol
   - which metrics decide promotion
   - which metrics are only diagnostic

4. failure log or architecture debt note
   - known stale docs
   - known missing provenance
   - known temporary heuristics

## Current Recommended Reading Order

For a new engineer:

1. this file
2. `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\README.md`
3. `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\README.md`
4. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\README.md`
5. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\LABEL_POLICY.md`
6. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\SPLIT_POLICY.md`
7. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\README.md`
8. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v1\README.md`
9. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\README.md`
10. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v3\README.md`
11. `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\README.md`

## Commands

Examples only. Do not assume these should always be rerun.

Layer 2 ablations:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py
```

Pretrain on one Layer 2 experiment:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v2 --source-kind layer2_exp5
```

Pretrain the Layer2 full-set benchmark:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v4
```

Downstream v2:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\main.py
```

Downstream v4:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\main.py
```

Generate PNG charts from one or more run folders:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_charts.py D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\17-05-2026\v2_111705
```

Backfill optional models on an existing `v2` run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\backfill_optional_models.py --run-dir D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\<DD-MM-YYYY>\<run_name>
```

## Limits

- This file is a system snapshot, not a source of truth for metrics.
- If this file and module code disagree, code and generated artifacts win until the documentation is corrected.
