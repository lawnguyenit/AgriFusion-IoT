# agrifusion (telemetry backend)

## Purpose

`src/agrifusion` owns the accepted backend stages from raw telemetry
ingestion through canonical preprocessing.

The package is responsible for:

- fetching or loading telemetry sources for Layer0;
- loading local telemetry sources;
- preserving source provenance;
- building canonical records;
- deriving deterministic low-level features, without assigning benchmark
  labels or model outputs.

The package is not responsible for:

- training or evaluating models;
- creating benchmark labels;
- mutating raw Layer0 evidence in place.

## Current structure

```text
src/agrifusion/
|-- cli.py       `agrifusion` command (python -m agrifusion)
|-- settings/    env, paths, BackendSettings (injected into the pipelines)
|-- io/          storage, JSON and table helpers
|-- ingest/      Layer0: raw telemetry ingestion into Layer0 artifacts
|-- canonical/   Layer1: canonical telemetry preprocessing
`-- cloud/       Firebase RTDB client (imported only for --source firebase)
```

## Data flow

```text
Firebase RTDB / JSON export
-> src/agrifusion/ingest
-> output/Layer0
-> src/agrifusion/canonical
-> output/Layer1
-> research/agrifusion_research consumers
```

## Notes

- Layer1 now uses one canonical history table as its source of truth.
- Layer0 and its Firebase adapter now live under `src/agrifusion`, not a
  separate `Services` package.
- Sensor-specific `sht30/*` and `npk/*` artifacts under
  `output/Layer1` are compatibility outputs derived from canonical
  rows, not independent processing pipelines.
- The former `layer2/` feature builders had no importers and were removed.

## Risks

- Changing agrifusion outputs can affect `research/agrifusion_research` and `Frontend` consumers.
- Deleting compatibility outputs before migrating consumers will break
  downstream pipelines.
