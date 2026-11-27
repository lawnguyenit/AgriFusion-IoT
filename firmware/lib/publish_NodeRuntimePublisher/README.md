# NodeRuntimePublisher

Purpose: publish node runtime metadata to RTDB.

Writes in production:
- Node info
- Latest snapshot at `/Node2/latest/current`
- Latest polling metadata at `/Node2/latest/meta`

The production build does not write the auxiliary `/debug/Node2` branch.
Live-status, telemetry-debug, telemetry-channel, and status-event writers are
guarded by `APP_RTDB_DEBUG_PUBLISH_ENABLED` and can be re-enabled only for an
explicit cloud-diagnostic build.

Live status includes transport diagnostics such as signal validity/CSQ and,
when available, the local PDP IP plus the resolver source. Invalid modem
operator/error text and the `0.0.0.0` sentinel are not published as observed
values.

Main file:
- `src/NodeRuntimePublisher.cpp`

Important note:
- This library is useful for observability, but it can generate many RTDB writes if not throttled carefully.
