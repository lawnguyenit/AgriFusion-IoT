# Sim

Purpose: manage the SIM A768x/A767x modem as the cellular transport layer.

Responsibilities:
- UART AT handshake
- Numeric/verbose AT response handling
- Network registration checks
- GPRS connect/reconnect
- IP resolution and SIM network state reporting
- Basic Internet socket test

Main files:
- `src/SimA7680C.h`
- `src/SimA7680C.cpp`

Important config:
- `SIM_*`
- `USE_SIM_NETWORK`
