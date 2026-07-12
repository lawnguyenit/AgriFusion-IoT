# Backend Core

## Purpose

`Backend/Core` owns canonical telemetry processing after raw artifacts have
already been pulled into local storage by Layer0 services.

Core is responsible for:

- loading local telemetry sources;
- preserving source provenance;
- building canonical records;
- deriving deterministic low-level features;
- producing reusable downstream tables without assigning benchmark labels
  or model outputs.

Core is not responsible for:

- fetching Firebase or other external services directly;
- training or evaluating models;
- creating benchmark labels;
- mutating raw Layer0 evidence in place.

## Current structure

```text
Core/
|-- layer1/      canonical telemetry preprocessing
|-- fusion.py    SuperTable fusion from Layer1 compatibility histories
|-- layer2/      reusable benchmark-facing time-series feature builders
|-- canonical/   model-facing matrix builders
|-- contracts/   shared Core schema/version markers
`-- utils/       low-level helpers reused inside Core
```

## Data flow

```text
Layer0 raw local
-> Core/layer1
-> Backend/Output_data/Layer1
-> Core/fusion.py
-> Backend/Output_data/SuperTable
-> Core/canonical or Backend/Benchmark consumers
```

## Notes

- Layer1 now uses one canonical history table as its source of truth.
- Sensor-specific `sht30/*`, `npk/*`, and `meteo/*` artifacts under
  `Output_data/Layer1` are compatibility outputs derived from canonical
  rows, not independent processing pipelines.
- `fusion.py` replaced the older `Core/fusion/` package layout. References
  to the old directory are stale.
- `layer2/` is still active and used by benchmark dataset builders.

## Risks

- Changing Core contracts can affect `Services`, `Benchmark`, and
  `Frontend` consumers.
- Deleting compatibility outputs before migrating consumers will break
  downstream pipelines.
