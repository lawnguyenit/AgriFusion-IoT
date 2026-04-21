# DateTime

Purpose: small helpers for time synchronization and formatted time strings.

Main API:
- `syncTimeFromSIM()`
- `getCurrentTimeStr()`

Use case:
- Legacy/simple time utilities for modules that need a human-readable timestamp.

Notes:
- Current runtime flow mainly uses NTP and `time()` directly in `main.cpp`.
- Keep this library only if older code paths still reference it.
