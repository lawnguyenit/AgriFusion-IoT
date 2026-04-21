# OtaManager

Purpose: fetch OTA commands from RTDB and apply HTTP OTA updates.

Main features:
- Read OTA command payload
- Disable handled commands
- Perform the actual HTTP OTA transfer

Main file:
- `src/OtaManager.h`

Important config:
- `APP_RTDB_PATH_OTA_COMMAND`
- `APP_OTA_POLL_INTERVAL_MS`
