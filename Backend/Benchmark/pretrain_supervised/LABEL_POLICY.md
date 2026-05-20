# Label Policy

## Purpose

This document defines where downstream labels come from for the current benchmark system.

It is intentionally separate from model code because label semantics are a benchmark contract, not just an implementation detail.

## Current Source

Current downstream label merge uses:

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

The current merge is performed by:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v1\src\data\labels.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\src\data\embeddings.py`

## Current Label Columns

The downstream system currently reads these annotation columns when present:

- `event_source`
- `event_confidence`
- `event_reason`
- `event_primary`
- `event_labels`
- `big_label`

`big_label` is currently treated as the most stable top-level label source.
If `big_label` is missing, downstream falls back to `event_primary`.
If neither exists, the row is treated as `none`.

## Binary Policy

Current binary policy is:

- `big_label == "none"` -> `normal`
- `big_label != "none"` -> `abnormal`

This means the current binary target is broad.

It does **not** mean:
- only sensor anomaly,
- only environmental anomaly,
- or only intervention anomaly.

It means any annotated non-`none` event/context is currently treated as `abnormal`.

## Ternary Policy

Current ternary policy groups labels into:

- `normal`
- `environmental_context`
- `operational_or_intervention`

Current mapping:

- `weather_context` -> `environmental_context`
- `stress_context` -> `environmental_context`
- `system_timing` -> `operational_or_intervention`
- `sensor_fault_anomaly` -> `operational_or_intervention`
- `intervention_context` -> `operational_or_intervention`
- other non-`none` labels -> `operational_or_intervention`

## What `abnormal` Means Today

For the current benchmark, `abnormal` means:

- a row has some known event/context annotation,
- not necessarily a pure anomaly in the strict statistical sense.

So the model is currently best described as learning:

- `normal` vs `annotated_non_normal`

not:

- `normal` vs `all true unknown anomalies`

## Implications

1. A row can be labeled `abnormal` because of:
   - weather context,
   - intervention context,
   - sensor fault context,
   - system timing context,
   - or other rule-derived event group.

2. The current binary benchmark is useful for:
   - screening,
   - ranking,
   - representation comparison,
   - and downstream baseline selection.

3. The current binary benchmark is **not yet** a strict anomaly-detection ground truth.

## Current Gaps

These are still open:

1. The exact producer path for `big_label` inside the current benchmark tree is not fully documented.
2. The current benchmark merges all non-`none` events into a single abnormal bucket.
3. Unknown abnormal states that were never annotated are still effectively treated as normal during supervised training.

## Next Recommended Step

Before moving to stricter evaluation, create a second-stage label policy that separates:

- `known_normal`
- `known_abnormal`
- `unknown_or_unverified`

That will reduce the semantic overload currently carried by the single `abnormal` label.
