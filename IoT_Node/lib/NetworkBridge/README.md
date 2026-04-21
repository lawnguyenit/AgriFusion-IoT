# NetworkBridge

Purpose: expose one unified network API regardless of Wi-Fi or SIM transport.

Main API:
- `networkSetup()`
- `networkMaintain()`
- `networkIsConnected()`
- `networkSignalDbm()`
- `networkLocalIp()`
- `networkStatusCode()`
- `networkTransportName()`

Why it matters:
- `main.cpp` and publishers do not need transport-specific branching everywhere.
