# SoilMoistureProbe

Temporary serial-only diagnostic adapter for the assumed capacitive soil
moisture sensor v1.2 with an analog output.

Current wiring/configuration:

- `VCC -> 3V3`
- `GND -> GND`
- `AOUT -> GPIO1` (`SOIL_MOISTURE_ADC_PIN`)
- Serial monitor: `115200`

The probe prints a smoothed raw ADC value, sample minimum/maximum, and the
Arduino-calibrated ADC voltage. The current provisional endpoints are
`dry_air=3000` and `submerged=1200`, based on the ESP32 example in the
[ShillehTek v1.2 manual](https://shillehtek.com/blogs/shillehtek-product-manuals/capacitive-soil-moisture-sensor-v1-2-manual).
The first 22 air readings from the current unit (about raw 2967 / 2508 mV)
agree with that dry-air reference. The percent remains a relative air-to-water
index, not VWC or field-calibrated soil moisture; verify the wet endpoint on the
actual unit and soil before relying on it.

For hardware isolation, start the board with the sensing blade in air. The
boot cycle captures that reading as the air baseline. Each one-second cycle
then prints `delta_raw`, `delta_mv`, and `raw_window_relation` relative to that
baseline. Send `a` in the serial monitor to capture a fresh baseline before
repeating the transition. The expected direction for this common v1.2 design is
lower raw/voltage in water and higher raw/voltage after removal. A flat ADC
comparison cannot by itself distinguish a failed probe from AOUT/GND/wiring or
GPIO issues; measure AOUT against GND directly if the output stays flat.

The probe uses the same `SoilMoistureService` as `AppRuntime` and the combined
sensor test, so its ADC/calibration/error semantics are shared with the NPK
pipeline.

Set only `APP_SOIL_MOISTURE_TEST_MODE=1` in `Config.h`; keep the other
diagnostic selectors at 0. Then use the standard `esp32-s3-n16r8` environment
in the PlatformIO UI to Build/Upload. `DEBUG_MODE=1` enables the serial output.
The probe bypasses SHT30, DS18B20, NPK, SIM, Firebase, and production runtime.
Set `APP_SOIL_MOISTURE_TEST_MODE=0` after the bench test to restore production.
