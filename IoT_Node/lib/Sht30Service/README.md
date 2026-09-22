# Sht30Service

Purpose: production-facing SHT30 service with retry, validation, and JSON payload generation.

Built-in behavior:
- Re-init retry loop
- Multiple read attempts in one sample window
- Range validation
- Invalid streak tracking
- JSON payload generation for packet composition
- Initialization requires one successful real temperature/humidity measurement;
  an address ACK alone is not treated as a ready sensor.
- Debug output includes final read status, retry count, elapsed time, error, and
  valid temperature/humidity values.
- Failed initialization keeps the last I2C address-ACK/error code, init attempt
  count, probe result, and probe values in the payload's read-status diagnostics;
  this separates a missing bus from a responding sensor that returns invalid
  measurement bytes.
- Measurement reads use the explicit SHT3x single-shot high-repeatability command
  (`0x2400`), wait for conversion, require exactly 6 response bytes, and verify
  both CRC bytes before reporting transport success. Raw words, frame length,
  CRC status, and a specific measurement error are exposed separately from
  `sht_sample_valid`; therefore a CRC-valid all-zero frame is reported as an
  invalid sample rather than a valid environmental reading.
- The Node2 production profile uses the phase-1 low-speed I2C setup (10 kHz,
  100 ms after `Wire.begin`) with the currently configured SDA 6, SCL 7, and
  address `0x44`.

Main file:
- `src/Sht30Service.cpp`

Important config:
- `SHT30_*`
- `APP_SHT30_RETRY_INIT_MS`
