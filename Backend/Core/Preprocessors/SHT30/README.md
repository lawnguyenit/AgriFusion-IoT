# SHT30 Preprocessor

## Purpose

This folder contains the layer-2 preprocessing logic for the SHT30 air-climate stream.

The goal is to convert a raw SHT30 packet into a domain-ready snapshot with:

- normalized perception,
- trust scoring,
- short and medium memory windows,
- contextual hints for the air-climate domain agent.

## File Map

| File | Role |
| --- | --- |
| `__init__.py` | Exposes `SHT30Processor` to the shared preprocessing pipeline. |
| `SHT30_Data.py` | Builds the layer-2 output: perception, windows, context, anomaly hints, and layer-3 handoff payload. |
| `SHT30_Health.py` | Converts sensor/driver flags into a confidence score for downstream reasoning. |

## What `SHT30_Data.py` Produces

Each processed record contains:

- `perception`: air temperature, air humidity, sensor quality.
- `memory.windows`: rolling windows (`3h`, `6h`, `24h`, `72h`) for trend-aware reasoning.
- `context`: hour of day, transport, battery, and macro humidity trend.
- `inference_hints`: humidity spike, condensation risk, heat stress, and weather-driven likelihood.
- `layer3_interface`: compact output for the domain agent.

`temp_trend_short_horizon` is derived from the configured short trend window
(`window_hours[1]` when available), and `temp_trend_window_key` records which
window was actually used. This avoids hard-coding stale window labels when the
window configuration changes.

## What `SHT30_Health.py` Does

`SHT30_Health.py` translates driver certainty into a trust score.

Important: the penalty values in this file are **not copied from the Sensirion datasheet**. They are internal weights that tell the domain agent how much confidence to lose when the driver reports bad conditions.

The structure is based on:

1. hard driver signals:
   - `sht_read_ok`
   - `sht_sample_valid`
   - `sht_error`
   - `sht_invalid_streak`
   - `sht_retry_count`
2. the fact that SHT30 nominal accuracy is strong in normal operation
3. a need to sharply separate "sensor problem" from "real microclimate event"

## Provenance Of The Main Thresholds

### Datasheet anchored

| Item | Why it matters here |
| --- | --- |
| SHT30 nominal RH accuracy is around `+/-2%RH` and operating RH range is `0-100%RH` | The health model assumes the sensor is trustworthy when reads are valid, so anomaly thresholds in layer 2 are intentionally larger than raw sensor noise. |
| Typical temperature accuracy is around `+/-0.2C` and the operating temperature range is wide | This supports using broader domain thresholds such as heat-stress and condensation heuristics instead of tiny deltas near the sensor noise floor. |

### Internal heuristics that still need field calibration

| Threshold / weight | Current meaning |
| --- | --- |
| `HEAT_STRESS_TEMPERATURE_C = 31` | Early warning point for hot air stress in the current domain logic. |
| `AIR_STRESS_HUMIDITY_BASE_PCT = 80` | Humidity baseline used when composing the air-stress score. |
| `CONDENSATION_HUMIDITY_BASE_PCT = 85` | High-humidity base for condensation suspicion. |
| `HUMIDITY_SPIKE_DELTA_PCT = 7.5` | Deviation from the 24h mean considered large enough to flag a humidity spike. |
| `WEATHER_SHIFT_REFERENCE_PCT = 12` | Reference delta for scaling weather-driven likelihood. |
| `READ_FAIL_PENALTY = 0.35` | Large trust reduction because failed reads break the main sensing contract. |
| `INVALID_SAMPLE_PENALTY = 0.25` | Strong reduction because the packet itself says the sample should not be trusted. |

These are reasoning thresholds, not hardware limits. They should be tuned with real greenhouse/orchard data.

## Source Notes

The SHT30 capability references should come from Sensirion material, not from our heuristics:

- Sensirion SHT30 product page:
  https://sensirion.com/cn/products/catalog/SHT30-ARP-B
- Sensirion SHT3x datasheet family:
  https://sensirion.com/products/catalog/SHT3x-DIS

Use the vendor material for:

- accuracy,
- operating range,
- response-time expectations.

Use this folder's code for:

- trust downgrading,
- windowed context,
- handoff formatting,
- anomaly priors for layer 3.

## Design Intent

Layer 2 should answer:

- "What did the sensor read?"
- "How much should we trust it?"
- "What recent context should the domain agent remember?"

It should not answer:

- "Is the crop definitely under stress?"
- "Should we trigger the final alert?"

Those belong to layer 3.
