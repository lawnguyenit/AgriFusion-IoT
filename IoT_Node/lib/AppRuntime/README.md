# AppRuntime

Purpose: hold the high-level orchestration for the running node.

Responsibilities:
- Boot runtime services
- Create and own the sensor/network tasks
- Coordinate network, Firebase, OTA, buffering, and status publishing
- Keep `main.cpp` minimal

Why it exists:
- The application flow had grown too large for `src/main.cpp`.
- This library is the runtime shell around lower-level modules such as `Sim`, `FirebasePipeline`, `NodePacketBuilder`, and OTA helpers.
