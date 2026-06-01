# Fuzzy Logic Basic Benchmark Dataset

## Purpose

`fuzzy_logic_basic/` now owns benchmark dataset preparation only.

Its job is to turn local Layer1 histories into:

- one aligned benchmark CSV
- one managed real-labeled benchmark CSV
- Layer2 ablation exports
- Layer3 combo exports

It does not own the old fuzzy risk-inference chain anymore.

## Layout

- `main.py`
  - root entrypoint for the current dataset build
- `layer1/`
  - align local Layer1 histories into `flb_input_aligned.csv`
- `real_event_labeling/`
  - rebuild `flb_input_with_events.csv` from the aligned benchmark CSV plus Layer0 Firebase metadata
- `layer2/`
  - build `exp1..exp6` benchmark feature exports and retain `big_label`
- `layer3_combo/`
  - build `combo1..combo4` benchmark feature exports and retain `big_label`
- `dataset/`
  - generated benchmark CSVs and build reports

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`

## Generated Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp6.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\manifest.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_real_event_labeling_report.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_layer2_build_report.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_layer3_combo_build_report.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_dataset_build_report.json`

## Commands

Build the full current dataset package:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py
```

Build only the feature package and skip real labels:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-real-event-labeling
```

Rebuild only Layer1 + Layer2:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-layer3-combo
```

Reuse an existing aligned CSV and rebuild only engineered exports:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-layer1
```

Build only selected Layer2 experiments:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --layer2-experiments exp2 exp6 --skip-layer3-combo
```

Build only selected Layer3 combos:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py --skip-layer1 --skip-layer2 --layer3-combo-experiments combo2 combo4
```

Rebuild only the real labeled artifact:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\real_event_labeling\main.py
```

## Assumptions

- `layer1` is the only stage here that reads from `Backend/Output_data/Layer1`.
- `real_event_labeling` consumes `flb_input_aligned.csv` and Layer0 Firebase metadata keyed by `timestamp`.
- `layer2` and `layer3_combo` consume the labeled CSV by default and only retain `big_label` beyond their feature contract.
- All generated CSVs are benchmark dataset artifacts, not raw source of truth.
- The managed `flb_input_with_events.csv` always uses the aligned CSV as the feature source of truth.

## Risks / Limits

- The real label stage is still heuristic and depends on Layer0 Firebase metadata being available.
- `layer2` and `layer3_combo` currently write lightweight build reports, not dated run directories.
- If the aligned Layer1 schema changes, downstream benchmark contracts may need version bumps.
