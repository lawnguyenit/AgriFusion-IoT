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

## Merged: HTTP client (formerly lib SimHttpClient)


Purpose: provide a minimal HTTP(S) client over the modem's built-in `AT+HTTP*` engine for A76xx series modules.

Responsibilities:
- start and stop HTTP service with `AT+HTTPINIT` / `AT+HTTPTERM`
- set URL and content type with `AT+HTTPPARA`
- upload entity data with `AT+HTTPDATA`
- execute `GET/POST/PUT/PATCH/DELETE` through `AT+HTTPACTION`
- read headers and body for diagnostics

Use case:
- serve as the low-level transport for RTDB REST calls over SIM without relying on TinyGSM

HTTP-read payload extraction removes the modem's `OK` trailer for CRLF, LF, or
CR line endings and bounds the accumulated body by the modem-reported HTTP
body length, so a JSON body such as `null` reaches the RTDB caller intact.

## Merged: socket transport (formerly lib SimSocketTransport)


Thu vien nay cung cap duong socket raw-AT cho modem SIMCom ma khong phu thuoc vao thu vien socket ben ngoai.

Muc dich:
- test xem modem co mo duoc `NETOPEN/CIPOPEN` bang raw AT hay khong
- gui HTTP GET toi host test bang `CIPSEND`
- doc phan hoi bang `CIPRXGET`

Use case hien tai:
- chan doan khi modem co IP nhung van khong mo/giao tiep socket on dinh
- lam nen tang transport TCP/HTTP truc tiep bang AT command
