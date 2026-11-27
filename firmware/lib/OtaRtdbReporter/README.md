# OtaRtdbReporter

Purpose: publish OTA lifecycle events and status into RTDB.

Writes:
- Current OTA status
- OTA history events
- Pending events that were saved locally before the network returned

Used by:
- `main.cpp`
- `OtaBootGuard`
- `OtaStateStore`
