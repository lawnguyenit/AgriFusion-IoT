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
