# NPK Preprocessor

## Purpose

This folder contains the layer-2 preprocessing logic for the RS485 7-in-1 soil sensor stream.

The job of this layer is not to make the final agronomic decision. Its job is to:

1. normalize the raw packet into a stable schema,
2. score how trustworthy the current NPK reading is,
3. build time-window memory for downstream agents,
4. hand off a clean payload to layer 3.

## File Map

| File | Role |
| --- | --- |
| `__init__.py` | Exposes `NPKProcessor` to the shared preprocessing pipeline. |
| `NPK_Data.py` | Builds the layer-2 snapshot: perception, windows, context, inference hints, and layer-3 handoff payload. |
| `NPK_Health.py` | Computes trust/confidence for the NPK stream from transport flags, sensor flags, dry-soil risk, and power state. |

## What `NPK_Data.py` Produces

Each processed record contains:

- `perception`: `N`, `P`, `K`, soil temperature, humidity, pH, EC, sensor quality.
- `memory.windows`: rolling windows (`6h`, `24h`, `72h`) for trend-aware reasoning.
- `context`: hour of day, sample interval, transport, battery, moisture trend.
- `inference_hints`: early signals for layer 3 such as nutrient imbalance, salinity risk, dry-soil reliability risk, and possible leaching.
- `layer3_interface`: the compact handoff contract for the domain agent.

## What `NPK_Health.py` Does

`NPK_Health.py` converts packet-level certainty into `confidence`.

Important: the penalty values in this file are **not vendor calibration numbers**. They are internal trust weights for the domain agent.

The logic is grounded in three things:

1. hard protocol/driver signals from the packet:
   - `read_ok`
   - `frame_ok`
   - `crc_ok`
   - `npk_values_valid`
   - `retry_count`
   - `sensor_alarm`
2. vendor/manual caveats about this class of 7-in-1 sensor
3. field heuristics for how much trust should drop before layer 3 sees the sample

## Provenance Of The Main Thresholds

### Manual / vendor anchored

| Item | Why it matters here |
| --- | --- |
| Soil moisture accuracy is usually quoted around brown soil at `30%` and `60%` moisture | This is why the code now explicitly downgrades NPK trust when `soil_humidity_pct < 30`. |
| Many 7-in-1 manuals warn that NPK is not a true laboratory nutrient assay and may be storage/indicative only | This is why NPK confidence is treated more conservatively than a pure temperature/humidity sensor. |

### Internal heuristics that still need field calibration

| Threshold / weight | Current meaning |
| --- | --- |
| `LOW_MOISTURE_WARNING_PCT = 30` | Below this point, dry soil can distort ion transport and reduce NPK reliability. |
| `VERY_LOW_MOISTURE_PCT = 20` | Extra penalty because the dry-soil distortion risk becomes much harsher. |
| `LOW_MOISTURE_PENALTY = 0.25` | Trust reduction applied once the sample is below 30% soil humidity. |
| `VERY_LOW_MOISTURE_EXTRA_PENALTY = 0.10` | Additional trust reduction below 20%. |
| `SALINITY_RISK_BASELINE_US_CM = 1200` | Early warning point for high EC in the current domain logic. |
| `NUTRIENT_IMBALANCE_INDEX = 0.55` | Heuristic trigger for "ratio looks skewed enough to review". |
| `LEACHING_N_SHIFT_DELTA = -8` | Heuristic signal for a notable negative nutrient shift under wet conditions. |

These values are intentionally separated from protocol flags so they can be tuned later against real field labels.

## Source Notes

The current implementation was aligned against public product/manual material for 7-in-1 RS485 soil sensors:

- Example manual with the 30% / 60% moisture accuracy note:
  https://manuals.plus/ae/1005004657708331
- Example product specification showing the same moisture calibration points:
  https://www.htebd.com/npk-ph-ec-rs485-5-pin-sensor-7-in-1-for-agriculture/

One important caution from that manual class:

> NPK on this sensor family may be indicative/storage-oriented rather than a primary laboratory reference.

That is exactly why this folder separates:

- raw numeric value
- health/confidence
- downstream handoff readiness

## Design Intent

Layer 2 should be strict about trust and loose about interpretation.

That means:

- `NPK_Health.py` decides how believable the sample is.
- `NPK_Data.py` packages the sample with enough memory/context for the domain agent.
- The final agronomic conclusion belongs to layer 3, not here.
