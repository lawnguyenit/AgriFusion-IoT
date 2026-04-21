# Sht30Service

Purpose: production-facing SHT30 service with retry, validation, and JSON payload generation.

Built-in behavior:
- Re-init retry loop
- Multiple read attempts in one sample window
- Range validation
- Invalid streak tracking
- JSON payload generation for packet composition

Main file:
- `src/Sht30Service.cpp`

Important config:
- `SHT30_*`
- `APP_SHT30_RETRY_INIT_MS`
