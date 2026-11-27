# NPK

Purpose: read the 7-in-1 NPK/soil sensor over Modbus UART and convert it to JSON.

Built-in behavior:
- Up to 3 read attempts per confirmed register group
- Error code mapping
- Read duration and retry count tracking
- Per-field `field_validity` evidence for every decoded value
- Separate `field_value_validity` so a valid Modbus frame containing an
  implausible value is not treated as a valid measurement
- Empirical EC proxy reconstruction from the three N/P/K registers when the
  EC register is unavailable; the result is written directly to `npk.ec` and
  serialized with the same public EC shape as the phase-1 output
- Explicit `unsupported_default_zero` source for soil humidity when no
  external moisture source is attached, plus external adapters that let
  DS18B20 and `SoilMoistureService` replace the missing NPK soil-temperature
  and soil-humidity channels without changing the NPK schema
- Raw register values, conversion rules, selected register map, and per-group
  status/attempt diagnostics
- JSON payload generation for upstream upload

Read-map order:
- The Node2 production profile sets `NPK_LEGACY_FULL_MAP_ENABLED=0`, so normal
  wake cycles use the confirmed sparse map directly and do not spend a retry
  window on the known non-responding contiguous block. The legacy probe below
  remains available for deliberate matrix/profile testing.
- The phase-1 map is probed first when `NPK_LEGACY_FULL_MAP_ENABLED=1`:
  `9600 8N1`, slave ID `1`, FC03 holding registers `0x0000..0x0006`.
  Decoding is exactly the phase-1 implementation: humidity `reg0/10`,
  temperature `reg1/10`, EC `reg2`, pH `reg3/10`, and N/P/K `reg4..reg6`.
- If that contiguous request times out or otherwise fails, the reader falls
  back to the Node2 profile confirmed by the physical matrix:
  pH `0x0006` and N/P/K `0x001E..0x0020`, both holding-register FC03 reads.
- The selected map is emitted as `read_map`. The legacy probe status is kept
  even when the sparse fallback succeeds, so the next physical log can show
  whether the phase-1 profile is actually supported by this sensor/path.

`field_validity` means that the corresponding register transaction returned a
valid protocol response. `field_value_validity` means that the decoded value
passes the current semantic range checks. In particular, a pH response with
raw `0x0000` becomes decoded `0.0`, remains visible in raw/test diagnostics,
but is marked `ph_state=frame_ok_value_invalid` and is not promoted into the
canonical soil values by the diagnostic reporter. A timeout is instead shown
as `ph_state=no_response`.

`npk_values_valid` becomes true only when the selected map read succeeded, all
measured fields are semantically valid, either a configured unsupported
humidity default or a valid external moisture value is available, and at
least one nutrient signal is present. When
`AppRuntime` supplies a valid DS18B20 reading, `temp` is marked semantically
valid with `field_source.temp="ds18b20"` and
`conversion.temp="ds18b20_raw/16.0"`; the Modbus-only protocol validity map
remains separate.
When `AppRuntime` supplies a calibrated moisture reading, `hum` remains the
existing NPK humidity field with `field_source.hum="soil_moisture_v1_2"` and
`field_value_validity.hum=true`; `field_validity.hum` remains Modbus evidence
and is therefore false. Raw ADC, mV, calibration, error, conversion method,
and 10–15 cm installation-depth metadata are retained in `external_sources`.
An uncalibrated or failed read keeps the source/error diagnostics but serializes
`hum` as null.
The default-zero fields remain false in `field_value_validity` and are marked
in `field_defaulted_zero`; this separates schema compatibility from observed
measurements. A production or diagnostic caller may explicitly include confirmed partial
fields in the canonical record; semantic-invalid fields remain null there.

The current Layer1 calibration used by Node2 is:

```text
EC = round(104.537608 + 0.33430017*N + 0.92924061*P + 0.99130859*K)
```

This is a project calibration/proxy, not a new Modbus register conversion.
The public NPK JSON intentionally exposes only the ordinary EC field and
`raw_register` conversion shape used by phase 1; the internal calibration
implementation is not serialized as an EC-source/formula diagnostic.

Main files:
- `src/NPK.h`
- `src/NPK.cpp`

Important config:
- `NPK_TX_PIN`
- `NPK_RX_PIN`
- `NPK_BAUDRATE`
- `NPK_EC_INFERENCE_ENABLED` and the `NPK_EC_INFERENCE_*` coefficients
- `NPK_UNSUPPORTED_SOIL_CLIMATE_AS_ZERO`
- App-level fail policy in `Config.h`
