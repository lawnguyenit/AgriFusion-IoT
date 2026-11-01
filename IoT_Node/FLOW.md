# Node2 production flow

`src/main.cpp -> AppEntry -> AppRuntime` selects production when every diagnostic
selector in Config.h is zero. PlatformIO environment: `esp32-s3-n16r8`.

1. Opening initializes storage and sensor buses, then establishes SIM HTTP,
   clock and Firebase readiness. SHT30 measures directly after one Wire.begin;
   an ACK or valid CRC alone does not establish a valid sample.
2. Collection reads NPK, SHT30 and the external soil sensors. DS18B20 and Soil
   V2 fill the existing soil temperature/moisture fields. Zero N/P/K yields zero
   derived EC; unavailable pH retains the approved explicit default zero.
   Rejected SHT air readings are null; raw/observed values remain diagnostics.
   `packet_built` reports serialization, while per-sensor validity and the node
   `sensor_alarm` report acquisition health. The NPK-specific alarm stays local.
3. Finalization publishes the **live sample first**. RawTelemetryReporter checks
   the dated Node2 timestamp path, accepts JSON null as absent, and writes once.
   A confirmed existing record is a duplicate success. JSON/transport failures
   buffer the live record. A confirmed PUT is not undone by a latest failure;
   the latter is explicitly reported as `telemetry_saved_latest_failed`.
4. After live success, FirebasePipeline replays at most four network entries,
   stopping network attempts after the first failure. `REPLAY` logs distinguish
   these attempts from `LIVE`. Unknown or previously reconstructed sampling times
   are held locally, counted as `held_time`, without changing their timestamps.
   Malformed and unattempted lines are retained; `deferred` counts deferred work.
   The remaining queue is written to a staging file and renamed only after a
   complete write. Already published reconstructed records need explicit manual
   review; this firmware does not mutate historical cloud records.
5. Live success selects the normal 900-second sleep; a buffered live sample uses
   the configured 300-second retry. Backlog outcomes do not replace live status.

Transport ownership: RTDB callers -> RtdbRestClient -> SimHttpClient ->
HttpReadFrame. The decoder waits beyond initial OK, reads exactly the declared
HTTPREAD bytes, preserves chunk boundaries and whitespace, and consumes the
modem trailer. AT completion matches full result lines, so HTTP status text
containing OK does not end HTTPHEAD early. `pending_file` is a boolean, while
held/deferred/replayed/failed are record counts. HTTP 200 with incomplete body yields `rtdb_body_incomplete`.
Complete malformed JSON logs its length and parse error without payload data.

The standalone probes remain diagnostic entry points. Passing a probe proves
only that tested hardware sequence; production integration still needs device
validation. Local framing tests cover fragmented modem replies and long JSON;
the PlatformIO build checks the production entry and module integration.
