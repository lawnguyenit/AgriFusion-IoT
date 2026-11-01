# SimNode2Probe

SIM uplink smoke test. It does not initialize or read sensors and does not
enter `AppRuntime`.

At boot it initializes the already-powered SIM modem over the configured UART
(ESP GPIO17 TX and GPIO16 RX), runs the existing cloud HTTP transport check,
then writes the current uptime in seconds as a JSON integer to
`/debug/Node2/telemetry_probe` using the SIM-backed `RtdbRestClient`. This probe
does not toggle modem power-enable or PWRKEY pins. If setup, transport, or the
RTDB write fails, it waits 5 seconds after that attempt finishes and retries
the full test. The initial boot-settle wait is used only on the first attempt;
retries keep the modem powered and start AT probing without that extra wait. If
the AT UART is unresponsive, the failure snapshot is printed without issuing
additional timed-out AT queries. After a successful RTDB write, it stops retrying. The diagnostic
path is a single-value location and each successful retry replaces its
previous value. The probe does not write canonical `/Node2/telemetry` or
`/Node2/latest` records.

Read the serial output at 115200 baud:

- `[SIM][CLOUD] stage=cloud_transport_ready...` indicates SIM HTTP reached the
  internet test endpoint.
- `[SIM][RTDB_TEST] ok=1 ... http=2xx ...` indicates the authenticated RTDB
  debug write succeeded. The exact successful HTTP status is shown in the log.
- `skipped` identifies setup, transport, or local RTDB configuration failure;
  after a failed attempt, `[SIM][RTDB_TEST] next_attempt_in_ms=5000` marks the
  next retry. A successful write prints `complete; successful write, retry stopped`.

This validates modem HTTP plus RTDB write access only; it does not test sensor
collection or the production telemetry schema.
