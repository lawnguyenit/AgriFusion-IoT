# Layer2 Benchmark Exports

## Purpose

`layer2/` builds the single-window benchmark feature exports used by:

- `pretrain_supervised/v2`
- `pretrain_supervised/v4`
- `direct_benchmark` raw control arms `v2`, `v4`, `v5`

This stage consumes `flb_input_with_events.csv` by default and writes feature-engineered benchmark CSVs.
Each export retains `big_label` only, without carrying the full event-audit payload from the real-label source file.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp6.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_layer2_build_report.json`

## Experiment Meaning

- `exp1`
  - base Layer1 columns + one-step deltas
- `exp2`
  - `exp1` + 3h window features
- `exp3`
  - `exp1` + 8h window features
- `exp4`
  - `exp1` + 24h window features
- `exp5`
  - `exp1` + air-humidity saturation persistence features
- `exp6`
  - full Layer2 feature set

## Commands

Build all Layer2 exports:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py
```

Build one export:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py --experiment exp3
```

Build Layer2 through the root pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-layer3-combo
```

## Assumptions

- All temporal windows are backward-looking.
- Layer2 owns benchmark feature engineering, not label generation.
- Train-facing exports keep `big_label` only when the source CSV already carries labels.
- The build report records which exports were requested and which files were written.

## Risks / Limits

- Early rows can contain incomplete lookback information depending on the feature horizon.
- This stage does not validate or create `flb_input_with_events.csv`; it only reuses it when present.
