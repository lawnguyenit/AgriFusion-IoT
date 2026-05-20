# Layer2

## Purpose

- Convert the aligned Layer1 CSV into several ablation CSVs for benchmark pretraining.
- Isolate one feature group per experiment where possible so the benchmark can answer which temporal horizon actually matters.

## Current experiments

- `Exp1`: `L1 + delta`
- `Exp2`: `L1 + delta + 3h window`
- `Exp3`: `L1 + delta + 8h window`
- `Exp4`: `L1 + delta + 24h window`
- `Exp5`: `L1 + delta + saturation`
- `Exp6`: full `L2` set
  - used as the full-set benchmark export consumed by `pretrain_supervised/v4`

## Input

- Default input:
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`

## Output

- Written to the shared dataset root:
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp6.csv`

## Command

Run all Layer2 ablations:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py
```

Run one experiment:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py --experiment exp3
```

## Assumptions

- All windows are strict backward-looking.
- `pH`, `N`, `P`, `K`, `ec_npk_consistency_score`, and `ec_npk_consistency_flag` stay out of the main ablation dataset.
- `air_humidity_saturation_flag` uses the current saturation threshold configured in Layer2.

## Limits

- `L3` relational features are handled later, not here.
- The full dataset still depends on enough lookback history for the longer windows.
- This is an ablation benchmark, not the final clinical/nutrient inference layer.
