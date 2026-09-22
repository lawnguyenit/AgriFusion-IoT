# SimHttpClient

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
