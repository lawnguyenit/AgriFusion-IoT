# NPK

Purpose: read the 7-in-1 NPK/soil sensor over Modbus UART and convert it to JSON.

Built-in behavior:
- Up to 3 read attempts per sample
- Error code mapping
- Read duration and retry count tracking
- JSON payload generation for upstream upload

Main files:
- `src/NPK.h`
- `src/NPK.cpp`

Important config:
- `NPK_TX_PIN`
- `NPK_RX_PIN`
- `NPK_BAUDRATE`
- App-level fail policy in `Config.h`
