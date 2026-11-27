# RawTelemetryReporter

Purpose: normalize sensor payloads into deterministic raw telemetry records before RTDB upload.

Responsibilities:
- Build the canonical telemetry record
- Generate deterministic event IDs
- Map packet data into telemetry layout
- Preserve DS18B20 provenance inside the existing NPK soil-temperature field
- Preserve useful network diagnostics in `sim_record.network`: signal validity/CSQ,
  usable local PDP IP and its resolver source, and validated operator metadata
- Write raw telemetry to `/Node2/telemetry/<date>/<event>` (the root comes
  from `APP_RTDB_PATH_NODE_TELEMETRY` and remains peer-level with Node1)

When `RawTelemetryRecordContext.includePartialSensorValues` is enabled by the
Node2 production configuration or an explicit diagnostic caller, NPK fields are
mapped into `sensor_record.values` when their field-specific value validity is
true or when the library explicitly marks a field as a defaulted zero. A
calibrated/provisional moisture-v1.2 replacement is mapped to the existing
`soil_moisture_pct` field; DS18B20 is mapped to the existing `soil_temp_c`
field. Both retain compact source/validity metadata in `read_status`.
Uncalibrated or failed moisture remains null while its raw ADC/error evidence
is retained. EC inferred from N/P/K remains in the normal `soil_ec_us_cm`
field. A valid Modbus frame with an implausible decoded value (for example pH
`0.0`) remains visible as protocol/read evidence but is kept null as a
canonical measurement. Older payloads without per-field validity fall back to
the legacy maps. This prevents valid N/P/K/EC fields from being discarded
merely because pH is semantically invalid.

The production reporter writes a compact `read_status`: field-level validity,
source, pH protocol/value state, EC measurement kind, moisture calibration
status/profile/semantics, and essential raw moisture/depth values. Large
validity/raw-register/map objects are retained only for invalid or failed NPK
reads. SHT30 valid reads keep compact status; invalid/error reads retain frame,
CRC, raw, and observed-value diagnostics, including the known `-45 C/0%`
case.

Invalid sentinel values are not promoted as observations: `0.0.0.0` is omitted
from `local_ip`, and modem error text is omitted from `operator`. Public/NAT IP
is intentionally not part of production telemetry; it remains a smoke-test
diagnostic only.

Before writing a dated event, the reporter reads that exact RTDB path for
idempotency. A valid RTDB JSON `null` is classified as "path absent" and the
record is written; only another valid JSON value is classified as a duplicate.
Empty or malformed GET bodies fail closed and are reported as an RTDB read
error, so they cannot incorrectly suppress telemetry and still update `latest`.

Main file:
- `src/RawTelemetryReporter.cpp`

Used by:
- `FirebasePipeline`
- `NodeRuntimePublisher`
