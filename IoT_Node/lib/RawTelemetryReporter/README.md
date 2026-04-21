# RawTelemetryReporter

Purpose: normalize sensor payloads into deterministic raw telemetry records before RTDB upload.

Responsibilities:
- Build the canonical telemetry record
- Generate deterministic event IDs
- Map packet data into telemetry layout
- Write raw telemetry to `/telemetry/<date>/<event>`

Main file:
- `src/RawTelemetryReporter.cpp`

Used by:
- `FirebasePipeline`
- `NodeRuntimePublisher`
