# Telemetry Runtime Simulator

## Purpose

This module injects deterministic demo telemetry into Firebase RTDB so the server lifecycle can be demonstrated end-to-end without waiting for a physical device.

The runtime path now uses the standardized Firebase client boundary in `Services/clients/firebase_rtdb.py`.

It now supports two runtime demo modes:

- bootstrap a normal baseline for `2026-05-20 00:00 -> 12:00`
- inject a post-12:00 event episode made of multiple telemetry records

The mock date defaults to `2026-05-20` so demo records are easy to find and delete.

## Input

- Firebase latest payload under `Node1/latest/current`
- Firebase latest metadata under `Node1/latest/meta`
- Optional existing day payload under `Node1/telemetry/2026-05-20`
- Template id `0..4`

## Templates

- `0`: `normal_context`
- `1`: `packet_loss_outage`
- `2`: `water_deficit`
- `3`: `rain_humid_context`
- `4`: `fertigation_spike`

For runtime 4-class diagnosis:

- `3` and `4` both map to `moisture_or_intervention_context`

## Output

Firebase RTDB writes:

- `Node1/telemetry/<date>/<event>`
- `Node1/latest/current`
- `Node1/latest/meta`
- `Node1/live`
- `Node1/status_events/<event>_demo`

## Commands

Inject a single-record demo sample:

```powershell
python Backend\main.py --inject-telemetry-template 0
```

Bootstrap the normal baseline for `20/5` from midnight to noon:

```powershell
python Backend\main.py --demo-bootstrap-day --server-cycle-skip-layer25
```

Inject a post-noon water-deficit episode:

```powershell
python Backend\main.py --server-cycle-demo --inject-telemetry-template 2 --server-cycle-skip-layer25
```

Inject a packet-loss episode with a controlled gap:

```powershell
python Backend\main.py --server-cycle-demo --inject-telemetry-template 1 --inject-packet-gap-minutes 64 --server-cycle-skip-layer25
```

## Assumptions

- Firebase already contains a valid normalized `latest/current` payload that can be used as a structural seed.
- Demo episodes are deterministic and overwrite the same `2026-05-20` timestamps on repeated runs.
- The baseline is expected to be prepared first before running post-12:00 episodes.

## Risks / current limits

- Packet loss is approximated by a controlled timestamp gap plus recovery records, not by replaying a real communication outage.
- Event episodes are template-driven for demo purposes and are not meant to replace benchmark/train datasets.
- Repeated demo runs on the same date overwrite the same timestamp keys, which is useful for cleanup but means the date should remain reserved for demo.
