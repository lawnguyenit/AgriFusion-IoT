# FirebasePipeline

Purpose: orchestrate upload, fallback buffering, and replay of telemetry to Firebase RTDB.

Responsibilities:
- Initialize Firebase clients
- Build upload context
- Push payloads online
- Buffer payloads offline into LittleFS
- Replay buffered payloads when the network returns

Key files:
- `src/FirebasePipeline.h`
- `src/FirebasePipeline.cpp`

Important config:
- `APP_FIREBASE_*`
- `APP_OFFLINE_RAW_FILE`
- `APP_OFFLINE_REPLAY_INTERVAL_MS`
