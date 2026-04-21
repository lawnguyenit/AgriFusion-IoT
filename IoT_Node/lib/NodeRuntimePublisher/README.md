# NodeRuntimePublisher

Purpose: publish node runtime metadata to RTDB.

Writes:
- Node info
- Live status
- Telemetry debug channel
- Telemetry channel counters
- Status transition events

Main file:
- `src/NodeRuntimePublisher.cpp`

Important note:
- This library is useful for observability, but it can generate many RTDB writes if not throttled carefully.
