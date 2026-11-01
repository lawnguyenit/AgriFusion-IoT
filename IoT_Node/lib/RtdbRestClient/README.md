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
- `getRawJson()` preserves the RTDB response body, including the valid JSON
  literal `null` returned for a missing path; callers decide existence after
  parsing the body.

SIM transport body-length failure is reported as `rtdb_body_incomplete` with
expected/received byte counts, distinct from authentication or JSON errors.
