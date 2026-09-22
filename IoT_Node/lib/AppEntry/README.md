# AppEntry

Purpose: keep `src/main.cpp` disposable by moving mode selection and app startup into a library entrypoint.

Responsibilities:
- initialize debug serial once
- select between the serial-only full-sensor probe, optional moisture-v1.2/SHT30/DS18B20/raw diagnostic paths, and the real `AppRuntime` path, where `Ds18b20Service` and `SoilMoistureService` are part of the normal NPK collection pipeline
- keep `main.cpp` as a thin wrapper only

Main files:
- `src/AppEntry.h`
- `src/AppEntry.cpp`
