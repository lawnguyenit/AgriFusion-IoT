# Config

Purpose: centralize project-wide configuration for the node.

What lives here:
- Debug port and baud rate
- Network selection and SIM pins/APN
- Node identity and Firebase/RTDB paths
- OTA, timing, task, queue, and sensor policy constants

Main file:
- `src/Config.h`

Notes:
- This is the first place to edit when changing deployment parameters.
- `main.cpp` and several libraries now depend on these values instead of hardcoded literals.
