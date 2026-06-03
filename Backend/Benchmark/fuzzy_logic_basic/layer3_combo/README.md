# Layer3 Combo Benchmark Exports

## Purpose

`layer3_combo/` builds multi-window benchmark exports on top of the labeled Layer1 benchmark dataset.

These exports are used by:

- `pretrain_supervised/v3`
- `direct_benchmark` raw control arm `v3`

This stage is separate from `layer2` so combo experiments stay distinct from the single-window ablation family.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_layer3_combo_build_report.json`

## Combo Meaning

- `combo1`
  - base columns + 3h and 8h windows
- `combo2`
  - `combo1` + one-step deltas
- `combo3`
  - base columns + 3h, 8h, and 24h windows
- `combo4`
  - `combo3` + one-step deltas

## Commands

Build all combos:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\main.py
```

Build one combo:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\main.py --experiment combo2
```

Build combos through the root pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-layer2
```

## Assumptions

- Combo exports reuse the same labeled Layer1 base as Layer2.
- This stage changes feature composition only; it does not generate labels.
- Train-facing exports keep `big_label` only when the source CSV already carries labels.
- The build report records the selected combos and generated files.

## Risks / Limits

- Combo exports still depend on enough lookback history for longer windows.
- This stage does not create or validate the real labeled CSV.
