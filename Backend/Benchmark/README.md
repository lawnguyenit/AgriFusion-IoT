# Benchmark Workspace

## Purpose

`Backend/Benchmark` is the research workspace for:

- benchmark dataset preparation
- embedding pretraining
- downstream supervised experiments
- raw-feature control arms
- augmented real+synthetic context benchmarks
- report generation from frozen artifacts

This tree is separate from `Backend/Services` and `Backend/Core` so benchmark code can evolve without changing the production data pipeline.

## Current Layout

- `common/`
  - shared benchmark path registry
- `fuzzy_logic_basic/`
  - current benchmark dataset builder
  - owns `layer1`, `real_event_labeling`, `layer2`, and `layer3_combo`
- `pretrain_supervised/`
  - embedding pretrain plus downstream `v0..v4`
- `direct_benchmark/`
  - raw-feature control arm on `v0..v5`
- `ft_transformer_benchmark/`
  - FT-Transformer arm on the same raw-feature ladder
- `tabpfn_benchmark/`
  - TabPFN arm on the same raw-feature ladder
- `context_classifier/`
  - real+synthetic canonical dataset build and multi-class training/report flow

## Dataset Ownership

### `fuzzy_logic_basic/`

This module now owns benchmark dataset preparation only.

Produced artifacts:

- `flb_input_aligned.csv`
- `flb_input_with_events.csv`
- `flb_l2_exp1.csv` .. `flb_l2_exp6.csv`
- `flb_l3_combo1.csv` .. `flb_l3_combo4.csv`
- `manifest.json`
- `flb_real_event_labeling_report.json`
- `flb_layer2_build_report.json`
- `flb_layer3_combo_build_report.json`
- `flb_dataset_build_report.json`

It no longer owns the old fuzzy risk-inference chain.

### `flb_input_with_events.csv`

This file is consumed by downstream benchmark families for labels and minimal context provenance.
It is rebuilt by the real-event-labeling stage inside `fuzzy_logic_basic/`.

Treat it as an upstream labeled artifact that lives in:

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

Current consumers:

- `pretrain_supervised/v0..v4`
- `direct_benchmark`
- `ft_transformer_benchmark`
- `tabpfn_benchmark`
- `context_classifier`

## Current Data Flow

### Flow A: benchmark dataset build

`Backend/Output_data/Layer1`
-> `Backend/Benchmark/fuzzy_logic_basic/layer1`
-> `flb_input_aligned.csv`
-> `Backend/Benchmark/fuzzy_logic_basic/real_event_labeling`
-> `flb_input_with_events.csv`
-> `Backend/Benchmark/fuzzy_logic_basic/layer2`
-> `flb_l2_exp1..exp6.csv`
-> `Backend/Benchmark/fuzzy_logic_basic/layer3_combo`
-> `flb_l3_combo1..combo4.csv`

### Flow B: embedding benchmark

`flb_input_aligned.csv`
or one of:
- `flb_l2_exp1..exp6.csv`
- `flb_l3_combo1..combo4.csv`

-> `Backend/Benchmark/pretrain_supervised/pretrain`
-> embedding checkpoints and split artifacts
-> `Backend/Benchmark/pretrain_supervised/v0..v4`

### Flow C: raw-feature control arms

`flb_input_aligned.csv`
plus optional engineered exports:
- `flb_l2_exp2.csv`
- `flb_l2_exp6.csv`
- `flb_l3_combo2.csv`

-> `direct_benchmark`
-> `ft_transformer_benchmark`
-> `tabpfn_benchmark`

All three families also consume `flb_input_with_events.csv` for labels.

### Flow D: real+synthetic context benchmark

`flb_input_with_events.csv`
and simulator outputs under `Backend/Simulator/outputs/<run_id>/`
-> `context_classifier`
-> canonical split-aware tabular and sequence datasets
-> augmented training outputs and reports

## Version Contract

- `v0`
  - nutrient/pH ablation before the Layer1 embedding baseline
- `v1`
  - Layer1 embedding baseline
- `v2`
  - Layer2 single-window ablation family `exp1..exp5`
- `v3`
  - Layer3 combo family `combo1..combo4`
- `v4`
  - Layer2 full-set benchmark `exp6`
- direct benchmark
  - raw-feature control arm `v0..v5`
- FT benchmark
  - FT-Transformer arm on the raw-feature ladder `v0..v5`
- TabPFN benchmark
  - TabPFN arm on the raw-feature ladder `v0..v5`
- context classifier
  - real+synthetic multi-class benchmark with its own build/train/report flow

The current version catalog lives in:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\version_catalog.py`

## Shared Policy Owners

- split policy:
  - `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\split_policy`
- label policy:
  - `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\LABEL_POLICY.md`
  - `D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\LABEL_POLICY.md`

## Current Limits

- The current real label stage is still heuristic and depends on the availability of Layer0 Firebase metadata.
- Simple dataset-builder stages still use lightweight build reports instead of full dated run directories.
