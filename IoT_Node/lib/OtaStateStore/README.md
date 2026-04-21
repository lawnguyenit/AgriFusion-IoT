# OtaStateStore

Purpose: persist OTA command state and pending events in local storage.

What it stores:
- Last handled OTA request ID
- Pending validation info
- Pending OTA event when RTDB is unavailable

Why it matters:
- OTA flow can survive reboot and temporary network loss.
