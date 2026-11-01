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

HTTPREAD now uses `HttpReadFrame` and reads declared payload bytes exactly. The
initial `OK` is an acknowledgement; completion follows the length-delimited
payload and `+HTTPREAD: 0` or trailing `OK`. Chunk whitespace and embedded
OK/ERROR text are preserved. Partial bodies fail with `http_body_incomplete`
(expected/received counts), even if the server returned HTTP 200. Header/action
AT replies match complete result lines: the text `OK` in `HTTP/1.1 200 OK`
does not terminate HTTPHEAD early. Framing follows the
SIMCom A76XX AT manual HTTPREAD section. Focused portable C++ checks:
`test/host/http_read_frame_test.cpp`.

Protocol reference: [SIMCom A76XX AT command manual, HTTPREAD](https://dfimg.dfrobot.com/60c1e008bddfc41c3293de80/wiki/7d2bd4a846a64ee7c14fbb3844242579.pdf).
