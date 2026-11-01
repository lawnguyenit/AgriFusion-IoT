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
- The current production profile leaves all diagnostic selectors at 0, so the standard `esp32-s3-n16r8` PlatformIO environment starts Node2 `AppRuntime`. Set `APP_NPK_MATRIX_TEST_MODE=1` only for the serial-only, read-only NPK Modbus matrix; return it to 0 after the bench run. `DEBUG_MODE=1` enables serial logs. `APP_SIM_NODE2_TEST_MODE=1` remains an opt-in SIM uplink diagnostic that retries setup/HTTP/RTDB write failures after 5 seconds and stops after the debug write succeeds at `/debug/Node2/telemetry_probe`. `APP_SIM_UART_LOOPBACK_TEST_MODE=1` selects a separate UART2 loopback diagnostic without SIM/network/Firebase.
- Soil V2 bench wiring is `VCC=3V3`, `GND=GND`, and `AOUT=GPIO1`; use the existing `esp32-s3-n16r8` environment in PlatformIO to Build/Upload.
- SHT30 bench wiring is `VCC=3V3`, `GND=GND`, `SDA=GPIO6`, `SCL=GPIO7`; the probe checks primary address `0x44` and diagnostic fallback `0x45` using the existing `esp32-s3-n16r8` environment.
- DS18B20 bench wiring is `VDD=3V3`, `GND=GND`, and `DQ=GPIO21`; add a 4.7 kOhm pull-up from DQ to 3V3 when available. Use the existing `esp32-s3-n16r8` environment.
- NPK bench UART uses `9600 8N1`, ESP RX=GPIO4 and ESP TX=GPIO5 through the existing RS485 transceiver. Confirm the sensor's rated supply voltage from its label/manual.
- Production node identity and Firebase paths are Node2: canonical records at `/Node2/telemetry`, newest snapshot at `/Node2/latest/current`, and backend polling metadata at `/Node2/latest/meta`. Auxiliary `/debug/Node2` publishing is disabled by default.
- `APP_ALL_SENSORS_TEST_MODE=1` selects a serial-only combined NPK/moisture/DS18B20/SHT30 probe; it does not upload to Firebase or enter deep sleep. The individual moisture/SHT30/DS18B20 selectors are also hardware-only and all diagnostic selectors are mutually exclusive. `DS18B20_PIPELINE_ENABLED=1` controls the reusable DS18B20 temperature source inside the normal AppRuntime pipeline; it fills the existing NPK `temp` field. `SOIL_MOISTURE_PIPELINE_ENABLED=1` controls the reusable moisture source inside the normal AppRuntime pipeline; it fills the existing NPK `hum` field when calibrated.
- Copy `src/Config.private.example.h` to `src/Config.private.h` for real Firebase credentials.
- `src/Config.private.h` is intentionally ignored by git so node secrets do not live in tracked source.
