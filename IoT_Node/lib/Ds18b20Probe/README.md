# Ds18b20Probe

Serial-only diagnostic adapter for the reusable `Ds18b20Service`. It runs
outside `AppRuntime`, SIM, Firebase, NPK, and deep sleep, then prints ROM
discovery, ROM CRC, scratchpad CRC, raw temperature, resolution, and decoded
Celsius values to the debug serial port.

## Wiring for the selected test pin

For the ESP32-S3-DevKitC-1 profile used by this repository:

- DS18B20 `VDD` -> ESP32 `3V3`
- DS18B20 `GND` -> ESP32 `GND`
- DS18B20 `DQ` -> ESP32 `GPIO21`

GPIO21 is not used by the current NPK, SHT30, or SIM configuration. The
firmware enables the ESP32 internal pull-up and a GPIO strong pull-up during
conversion so the no-external-resistor setup can be tried. The DS18B20 bus is
specified with an external pull-up of approximately 4.7-5 kOhm; add that
resistor from `DQ` to `3V3` if the scan or scratchpad CRC fails.

The diagnostic adapter is intended for one or a small number of devices on a
short bench wire. It does not write Firebase or production telemetry. The
normal `AppRuntime` path uses the sibling `Ds18b20Service`; a valid reading is
merged into the existing NPK soil-temperature field rather than published as
a separate DS18B20 sensor branch.

The diagnostic also reports the idle DQ level and a reset/presence result. If
presence is detected but ROM search returns no valid address, it tries a
single-device `SKIP ROM` read as a compatibility fallback.
