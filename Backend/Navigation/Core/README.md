# Backend Core

## Purpose

`Backend/Core` owns the accepted backend stages from raw telemetry
ingestion through canonical preprocessing, plus the reusable
benchmark-facing Layer2 feature builders that still consume Core outputs.

Core is responsible for:

- fetching or loading telemetry sources for Layer0;
- loading local telemetry sources;
- preserving source provenance;
- building canonical records;
- deriving deterministic low-level features;
- producing reusable temporal feature bundles without assigning benchmark
  labels or model outputs.

Core is not responsible for:

- training or evaluating models;
- creating benchmark labels;
- mutating raw Layer0 evidence in place.

## Current structure

```text
Core/
|-- infrastructure/ external adapters used by Core stages
|-- layer0/      raw telemetry ingestion into Layer0 artifacts
|-- layer1/      canonical telemetry preprocessing
|-- layer2/      reusable benchmark-facing time-series feature builders
`-- utils/       low-level helpers reused inside Core
```

## Data flow

```text
Firebase RTDB / JSON export
-> Core/layer0
-> Backend/Output_data/Layer0
-> Core/layer1
-> Backend/Output_data/Layer1
-> Core/layer2 or Backend/Benchmark consumers
```

## Notes

- Layer1 now uses one canonical history table as its source of truth.
- Layer0 and its Firebase adapter now live under `Backend/Core`, not a
  separate `Services` package.
- Sensor-specific `sht30/*`, `npk/*`, and `meteo/*` artifacts under
  `Output_data/Layer1` are compatibility outputs derived from canonical
  rows, not independent processing pipelines.
- `layer2/` is still active and used by benchmark dataset builders.

## Risks

- Changing Core outputs can affect `Benchmark` and `Frontend` consumers.
- Deleting compatibility outputs before migrating consumers will break
  downstream pipelines.
