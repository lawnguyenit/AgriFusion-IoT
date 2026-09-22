# AppRuntime

Purpose: hold the high-level orchestration for the running node.

Responsibilities:
- Boot runtime services and select the continuous or wake-cycle profile
- Run the wake-cycle phases in order: opening, collection, finalization
- Coordinate sensor sampling, network/cloud readiness, buffering, and status publishing
- Keep firmware-update control out of the runtime; OTA source remains separate and inactive
- Keep `main.cpp` minimal

Wake-cycle contract:

- Opening prepares LittleFS, sensor interfaces, modem/network, cloud transport, and time, including the configured retry window.
- Collection reads NPK/SHT30/DS18B20/moisture with their existing retry and alarm policies and builds the canonical packet without publishing. Valid DS18B20 and calibrated moisture values replace the missing NPK soil-temperature and soil-humidity channels before serialization; source and validity diagnostics remain additive.
- If the SHT30 returns a transport-valid but semantically invalid frame (for example `-45 C`/`0 %`), the raw observed values and error label remain in read-status diagnostics while canonical air values stay null.
- Finalization rechecks the current transport, replays backlog, uploads or buffers the packet, publishes status, and selects the next deep-sleep interval.

Production entry is restored through `IoT_Node/src/main.cpp -> AppEntry ->
AppRuntime`. The old NPK payload-fit harness remains in `main.cpp` behind
`#if 0` for repeatable diagnostics, but it is not the active runtime.

Why it exists:
- The application flow had grown too large for `src/main.cpp`.
- This library is the runtime shell around lower-level modules such as `Sim`, `FirebasePipeline`, `NodePacketBuilder`, and the sensor services.
