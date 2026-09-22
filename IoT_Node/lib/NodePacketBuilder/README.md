# NodePacketBuilder

Purpose: build the combined node packet from sensor payloads and runtime metadata.

What it combines:
- NPK payload
- SHT30 payload
- System/network metadata
- Firmware and partition metadata

Why it exists:
- Packet composition is domain logic and should not live inside `main.cpp` or task orchestration code.

Main API:
- `buildCombinedNodePacket(...)`

The normal packet contains `packet.npk_data`, `packet.sht30_data`, and
`packet.system_data`. DS18B20 is read by `AppRuntime` before packet creation
and is merged into `packet.npk_data.temp`; no separate DS18B20 packet or
canonical sensor branch is emitted.

Payloads are parsed into temporary documents and deep-copied into the combined
document. Production packets keep compact per-field validity/source/calibration
metadata and retain full raw NPK/SHT30 diagnostics only when a sensor sample is
invalid or a read fails. The serial-only `full_sensor_serial_only` test mode
keeps the verbose diagnostic payload so hardware evidence is not lost during
bring-up. This keeps the normal packet small without turning an error into a
missing record.
