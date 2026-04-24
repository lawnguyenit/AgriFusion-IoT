# RawTruthProbe

Purpose: run a reusable raw-AT forensic harness for the SIM path before the full application runtime is enabled again.

Responsibilities:
- power the modem path using the configured GPIOs
- call `setupSIM()` and collect a connectivity report
- dump key AT state for forensic logs
- test the primary raw HTTP path that is actually reusable for the next TLS/Firebase phase
- bootstrap time from `CCLK` or HTTP `Date` when possible

Main files:
- `src/RawTruthProbe.h`
- `src/RawTruthProbe.cpp`

Use case:
- isolate SIM, packet data, socket, and time issues without going through Firebase or the old app runtime
- serve as the clean entrypoint while rebuilding the transport stack from raw AT upward
