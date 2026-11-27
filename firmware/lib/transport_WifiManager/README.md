# WifiManager

Purpose: legacy Wi-Fi transport helper for ESP32 deployments that do not use SIM.

Main API:
- `setupWifi()`
- `checkWifi()`
- `printWifiInfo()`

Config:
- SSID and password are currently defined inside `src/WifiManager.h`.

Status:
- Kept for Wi-Fi mode support through `NetworkBridge`.
