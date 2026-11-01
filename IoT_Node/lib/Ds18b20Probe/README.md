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

To run the bench test, set only `APP_DS18B20_TEST_MODE=1` in `Config.h`, with
the other diagnostic selectors at 0. Use the standard `esp32-s3-n16r8`
environment in the PlatformIO UI to Build/Upload; `DEBUG_MODE=1` enables the
serial log at 115200 baud. A good run reports a found device with a valid ROM
CRC, then `scratchpad_crc=1`, `range_ok=1`, and a plausible `temp` in the
`[DS18B20][READ]` / `[DS18B20][RESULT]` lines. Set the selector back to 0 when
the bench test is complete to restore production behavior.
