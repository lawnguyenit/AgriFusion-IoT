# TransportStability

Purpose: provide a reusable transport diagnostic cycle that can be called from the raw harness now and from the real runtime later.

Responsibilities:
- run one canonical primary raw HTTP probe through `SimSocketTransport`
- bootstrap system time from SIM `CCLK` first, then HTTP `Date` if needed
- reuse the same probe result when building the SIM connectivity verdict
- print one coherent report for time, transport, and forensic AT state

Main files:
- `src/TransportStability.h`
- `src/TransportStability.cpp`

Use case:
- keep `main.cpp` thin and disposable
- avoid duplicating probe/time/report logic across harness code and future runtime code
- serve as the stable seam before adding TLS and then Firebase back on top
