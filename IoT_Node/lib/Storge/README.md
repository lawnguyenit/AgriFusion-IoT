# Storge

Purpose: simple LittleFS helpers for offline data persistence.

Main API:
- `setupStorage()`
- `saveOfflineData()`
- `processOfflineData()`

Current use:
- `FirebasePipeline` appends offline telemetry records to `APP_OFFLINE_RAW_FILE`.

Important note:
- Current implementation appends indefinitely and has no retention or max-size policy yet.
