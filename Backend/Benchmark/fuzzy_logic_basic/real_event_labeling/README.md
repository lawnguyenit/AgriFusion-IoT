# Real Event Labeling

## Purpose

This module rebuilds `flb_input_with_events.csv` directly from:

- `flb_input_aligned.csv`
- Layer0 Firebase metadata under `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data`

It is the current producer for real benchmark labels.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data\history\...`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data\new_raw\latest.json`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_real_event_labeling_report.json`

## Command

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\real_event_labeling\main.py
```

## Assumptions

- `timestamp` remains the join key between aligned benchmark rows and Layer0 raw metadata.
- `big_label` is the stable benchmark label source.
- `event_primary` is retained as a compact provenance hint.
- Detailed event flags remain in this artifact for audit and rule debugging, but downstream train-facing exports only keep `big_label`.
- `event_labels`, `event_source`, `event_confidence`, and `event_reason` are intentionally omitted from this rebuilt artifact because current downstream benchmarks do not require them.

## Risks / Limits

- The real label rules are still heuristic.
- If Layer0 Firebase metadata is missing or incomplete for some timestamps, labeling still runs but some row-level audit fields may stay empty.
- This module does not create synthetic labels and does not change the Layer2/Layer3 feature contract by itself.
