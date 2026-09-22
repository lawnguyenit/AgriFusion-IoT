# SoilMoistureProbe

Temporary serial-only diagnostic adapter for the assumed capacitive soil
moisture sensor v1.2 with an analog output.

Current wiring/configuration:

- `VCC -> 3V3`
- `GND -> GND`
- `AOUT -> GPIO1` (`SOIL_MOISTURE_ADC_PIN`)
- Serial monitor: `115200`

The probe prints a smoothed raw ADC value, sample minimum/maximum, and the
Arduino-calibrated ADC voltage. It reports `percent=NA` until
`SOIL_MOISTURE_AIR_ADC` and `SOIL_MOISTURE_WATER_ADC` are set from actual dry
and soaked measurements. This avoids presenting an unverified calibration as
an observed soil-moisture percentage.

The probe uses the same `SoilMoistureService` as `AppRuntime` and the combined
sensor test, so its ADC/calibration/error semantics are shared with the NPK
pipeline.

Enable only `APP_SOIL_MOISTURE_TEST_MODE` in `Config.h`; the probe bypasses
SHT30, DS18B20, NPK, SIM, Firebase, and the production runtime.
