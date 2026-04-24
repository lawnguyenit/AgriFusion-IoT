# AppEntry

Purpose: keep `src/main.cpp` disposable by moving mode selection and app startup into a library entrypoint.

Responsibilities:
- initialize debug serial once
- select between the raw harness path and the real `AppRuntime` path
- keep `main.cpp` as a thin wrapper only

Main files:
- `src/AppEntry.h`
- `src/AppEntry.cpp`
