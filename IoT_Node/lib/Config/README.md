# Config

Purpose: centralize project-wide configuration for the node.

What lives here:
- Debug port and baud rate
- Network selection and SIM pins/APN
- Node identity and Firebase/RTDB paths
- OTA, timing, task, queue, and sensor policy constants

Main file:
- `src/Config.h`
- `src/Config.private.example.h`

Notes:
- This is the first place to edit when changing deployment parameters.
- `main.cpp` and several libraries now depend on these values instead of hardcoded literals.
- Copy `src/Config.private.example.h` to `src/Config.private.h` for real Firebase credentials.
- `src/Config.private.h` is intentionally ignored by git so node secrets do not live in tracked source.
