# Telemetry Orchestrator

## Purpose

This module runs runtime demo lifecycles that connect Firebase telemetry to local Layer0/Layer1 processing and FT-based result publishing.

Internally, the orchestration path now calls the standardized `Layer0IngestionPipeline` and relies on the standardized Firebase client boundary in `Services/clients/firebase_rtdb.py`.

It now supports three orchestration paths:

1. one-shot latest-only server cycle
2. demo baseline bootstrap for `2026-05-20 00:00 -> 12:00`
3. post-12:00 demo episode cycle that syncs a telemetry `ts` range instead of only the single latest point

## Input

- `Backend/Services/.env`
- Firebase telemetry under `Node1/telemetry`
- Local Layer0/Layer1 pipeline already wired through `Backend/main.py`
- `Backend/Services/layer0_ingestion`

## Output

- Updated local artifacts under `Backend/Output_data`
- Updated Firebase `result`

## Commands

Run the original latest-only one-shot cycle:

```powershell
python Backend\main.py --server-cycle-once --server-cycle-skip-layer25
```

Prepare the demo-day baseline:

```powershell
python Backend\main.py --demo-bootstrap-day --server-cycle-skip-layer25
```

Run a post-noon episode demo and publish FT result:

```powershell
python Backend\main.py --server-cycle-demo --inject-telemetry-template 2 --server-cycle-skip-layer25
```

Packet-loss demo with a larger gap:

```powershell
python Backend\main.py --server-cycle-demo --inject-telemetry-template 1 --inject-packet-gap-minutes 64 --server-cycle-skip-layer25
```

## Assumptions

- The demo-day baseline is prepared first before post-noon episodes are injected.
- Runtime FT diagnosis consumes Layer1-aligned data; Layer2.5 is optional for these demo cycles.
- The mock date `2026-05-20` is reserved for demo cleanup.
- Layer0 ingestion naming has been standardized; legacy `exporters` imports are compatibility-only.

## Risks / current limits

- `--server-cycle-demo` syncs the post-noon telemetry window for one day, not a general-purpose arbitrary cross-day replay engine.
- If the demo date already contains stale post-noon records from old experiments, the safest flow is to re-run the bootstrap and then the episode you want to show.
- This remains a one-shot orchestration path, not a long-running watcher/daemon yet.
