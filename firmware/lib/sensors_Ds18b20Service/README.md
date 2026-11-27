# Ds18b20Service

Reusable DS18B20 1-Wire service for the IoT node.

Responsibilities:

- configure and precharge the DQ bus on the configured GPIO;
- discover valid DS18B20 ROM addresses and verify ROM CRC;
- start a conversion with the configured pull-up strategy;
- read and validate the 9-byte scratchpad CRC and temperature range;
- expose validated readings for the application pipeline; the JSON payload
  helper is retained for the serial-only diagnostic adapter.

The current production profile uses GPIO21, internal pull-up, and the
experimental GPIO strong-pull-up fallback validated on the short bench wire.
Use a normal external pull-up from DQ to 3V3 when available. In the normal
`AppRuntime` pipeline, a valid reading is applied to the existing NPK
`NPK_Data.temp` field, so downstream packets and canonical telemetry keep
using `npk_data.temp` and `soil_temp_c`. The NPK payload records
`field_source.temp="ds18b20"` and the DS18B20 raw conversion in
`external_sources`.

`Ds18b20Probe` is the serial-only diagnostic adapter. It uses this service and
does not duplicate the 1-Wire implementation.
