# DeviceContext

Purpose: store runtime identity for the current boot.

What it provides:
- Stable `deviceId`
- Per-boot `bootId`
- Wake/reset metadata
- Incrementing sequence number for telemetry records

Main file:
- `src/DeviceContext.h`

Why it matters:
- Firebase telemetry and live status use this context to tag every record deterministically.
