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

`SimNetworkState` exposes the observed local PDP IPv4 together with
`localIpValid`, `localIpSource`, and the raw modem `signalCsq`. CSQ values
`0..31` are valid readings; only `99` (or an unavailable response) is unknown.
`0.0.0.0` is kept only as an internal unknown sentinel and is never treated as
an observed address. IPv4 parsing validates a candidate at end-of-line as
well, because some AT responses terminate immediately after the address.
