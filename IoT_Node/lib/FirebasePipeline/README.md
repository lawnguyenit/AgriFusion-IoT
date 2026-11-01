# FirebasePipeline

Purpose: orchestrate upload, fallback buffering, and replay of telemetry to Firebase RTDB.

Responsibilities:
- Initialize Firebase clients
- Build upload context
- Push payloads online
- Buffer payloads offline into LittleFS
- Replay buffered payloads when the network returns
- Persist each valid-time record at `/Node2/telemetry/YYYY-MM-DD/<TS>`
- Update `/Node2/latest/current` only as the newest instantaneous snapshot and
  `/Node2/latest/meta` as its backend polling metadata

Key files:
- `src/FirebasePipeline.h`
- `src/FirebasePipeline.cpp`

Important config:
- `APP_FIREBASE_*`
- `APP_OFFLINE_RAW_FILE`
- `APP_OFFLINE_REPLAY_INTERVAL_MS`

The telemetry path is not a debug path. In the production build,
`APP_RTDB_DEBUG_PUBLISH_ENABLED=0` disables the auxiliary `/debug/Node2` writers;
serial diagnostics remain available. The debug writers can be re-enabled only
for an explicit cloud-diagnostic build and are separate from canonical
telemetry.

When debug logging is enabled, each direct upload reports the exact telemetry
path and one of `WRITE OK`, `DUPLICATE`, or `WRITE FAIL`, followed by a pipeline
summary. This makes the dated RTDB branch independently verifiable from the
serial log.

The idempotency GET is interpreted as JSON: RTDB's `null` response for a new
dated path permits the telemetry write. Empty or malformed GET bodies are
treated as a failed pre-write check, so `latest` is not advanced without a
confirmed dated record.

Wake finalization uploads the live sample before replay. A successful dated PUT
remains successful if latest publication or backlog replay fails; the detail
explicitly identifies latest failure. Replay attempts at most four network
records per call and defers the remaining records after the first failure.
Unknown-time and previously reconstructed-time records remain in the existing
local queue, unchanged, counted as `held_time`; they are never assigned the
current sample timestamp. `deferred` counts entries not attempted in this call.
Successful/duplicate confirmed events leave the queue, while failed, malformed
and held entries are preserved. Queue replacement is staged and checked before
rename; originals survive a failed replacement. These held records require
explicit time recovery; they do not trigger fake fresh events or block a live
sample. Numeric timestamp keys and Node2 RTDB paths remain compatible.
