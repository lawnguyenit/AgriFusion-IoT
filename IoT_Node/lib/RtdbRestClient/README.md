# RtdbRestClient

Purpose: expose a very small RTDB REST client for SIM mode on top of `SimHttpClient`.

Responsibilities:
- build RTDB REST URLs from the configured database URL and legacy token
- probe root access with a shallow read
- write JSON to fixed RTDB paths with `PUT` and `PATCH`
- remove probe nodes with `DELETE`

Scope:
- intentionally limited to the node's current needs
- does not try to replace the full Firebase client SDK
