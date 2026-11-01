# DateTime

Purpose: bootstrap and inspect system time for the ESP32 when the cellular path is being debugged without full cloud/TLS.

Main API:
- `syncTimeFromSIM()`
- `syncTimeFromHttpDate()`
- `timeLooksSane()`
- `getCurrentTimeStr()`

Current behavior:
- Reads modem `AT+CCLK?` through the raw SIM layer.
- Rejects invalid modem clock values such as the default `70/01/01`.
- Falls back to parsing the `Date:` header from a raw HTTP probe when `CCLK` is not trustworthy.

Use case:
- Bring time into a sane state before testing TLS or Firebase.
- Provide a reusable time bootstrap that does not depend on TinyGSM.
