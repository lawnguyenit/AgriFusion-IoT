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
- `APP_ALL_SENSORS_TEST_MODE=1` selects a serial-only combined NPK/moisture/DS18B20/SHT30 probe; it does not upload to Firebase or enter deep sleep. The individual moisture/SHT30/DS18B20 selectors are also hardware-only and all diagnostic selectors are mutually exclusive. `DS18B20_PIPELINE_ENABLED=1` controls the reusable DS18B20 temperature source inside the normal AppRuntime pipeline; it fills the existing NPK `temp` field. `SOIL_MOISTURE_PIPELINE_ENABLED=1` controls the reusable moisture source inside the normal AppRuntime pipeline; it fills the existing NPK `hum` field when calibrated.
- Copy `src/Config.private.example.h` to `src/Config.private.h` for real Firebase credentials.
- `src/Config.private.h` is intentionally ignored by git so node secrets do not live in tracked source.
