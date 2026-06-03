# Context Classifier Label Policy

## Purpose

This module upgrades the benchmark from broad binary abnormal detection to a smaller context-aware multi-class task.

The module currently supports two canonical label schemes.

### `five_class_v1`

- `normal_context`
- `packet_loss_outage`
- `rain_humid_context`
- `fertigation_spike`
- `water_deficit`

### `option2_4class`

- `normal_context`
- `packet_loss_outage`
- `water_deficit`
- `rain_or_fertigation_context`

In `option2_4class`, the former `rain_humid_context` and `fertigation_spike` labels are merged into the canonical label `rain_or_fertigation_context` to stabilize validation/test coverage while preserving a multi-class setup.

## Real Data Mapping

Real rows come from:

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

This CSV is treated as an upstream labeled artifact.
It is consumed here and rebuilt by the real-event-labeling stage inside `fuzzy_logic_basic/`.

The canonical builder maps the fuzzy benchmark labels into the selected contract.

For `five_class_v1`:

- `big_label == "none"` -> `normal_context`
- `big_label == "weather_context"` -> `rain_humid_context`
- `big_label == "intervention_context"` -> `fertigation_spike`
- `big_label == "stress_context"` -> `water_deficit`
- `big_label in {"system_timing", "sensor_fault_anomaly"}` -> `packet_loss_outage`

For `option2_4class`:

- `big_label == "none"` -> `normal_context`
- `big_label == "weather_context"` -> `rain_or_fertigation_context`
- `big_label == "intervention_context"` -> `rain_or_fertigation_context`
- `big_label == "stress_context"` -> `water_deficit`
- `big_label in {"system_timing", "sensor_fault_anomaly"}` -> `packet_loss_outage`

This keeps the label space aligned with the current synthetic scenarios while preserving provenance through:

- `context_label_raw`
- `event_primary`

## Synthetic Data Mapping

Synthetic rows come from the simulator outputs:

- `synthetic_flb_gap_aware.csv`

The canonical label is taken from `scenario_label` and then mapped into the selected scheme.

Supported synthetic labels before scheme mapping:

- `normal_context`
- `packet_loss`
- `rain_or_fertigation_context`
- `water_deficit`

Legacy simulator artifacts may still contain:

- `rain_humid_context`
- `fertigation_spike`

These legacy labels are normalized into `rain_or_fertigation_context` under the active 4-class contract.

Under `option2_4class`:

- `rain_humid_context` -> `rain_or_fertigation_context`
- `fertigation_spike` -> `rain_or_fertigation_context`
- `rain_or_fertigation_context` -> `rain_or_fertigation_context`
- `packet_loss` -> `packet_loss_outage`

## Packet-Loss Features And Cause Proxies

Packet loss cannot be learned reliably from absolute timestamp alone. The canonical dataset therefore adds explicit outage-aware fields:

- `loss_packet_count`
- `outage_duration_steps`
- `time_since_last_valid_step`
- `recovery_step_index`
- `nighttime_outage_flag`
- `sunrise_recovery_flag`

The canonical dataset also keeps packet-loss diagnosis metadata for inspection:

- `packet_loss_flag`
- `suspected_cause`
- `cause_confidence`

These fields are generated for both real rows and synthetic rows.

## Assumptions

- `packet_loss_outage` is currently the canonical system-outage class.
- Real `system_timing` and `sensor_fault_anomaly` rows are collapsed into `packet_loss_outage` until a richer system-fault taxonomy is introduced.
- Synthetic packet loss is represented primarily through missing/outage structure, not through arbitrary sensor-value distortion.
- `suspected_cause` is a rule-based hypothesis, not a hard ground-truth cause label.

## Limits

- The 5-class mapping is intentionally compact and may merge semantically different operational faults into the same class.
- Real data label provenance still depends on the quality of `big_label` and the upstream real-event-labeling rules.
- Real and synthetic canonical labeled snapshots are persisted separately by the build pipeline so provenance can be inspected without recomputing splits.
