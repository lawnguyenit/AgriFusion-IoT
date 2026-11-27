# Backend Core

## Purpose

`Backend/Navigation/Core` owns the accepted backend stages from raw telemetry
ingestion through canonical preprocessing.

Core is responsible for:

- fetching or loading telemetry sources for Layer0;
- loading local telemetry sources;
- preserving source provenance;
- building canonical records;
- deriving deterministic low-level features, without assigning benchmark
  labels or model outputs.

Core is not responsible for:

- training or evaluating models;
- creating benchmark labels;
- mutating raw Layer0 evidence in place.

## Current structure

```text
Backend/Navigation/Core/
|-- infrastructure/ external adapters used by Core stages
|-- layer0/      raw telemetry ingestion into Layer0 artifacts
|-- layer1/      canonical telemetry preprocessing
`-- utils/       low-level helpers reused inside Core
```

## Data flow

```text
Firebase RTDB / JSON export
-> Backend/Navigation/Core/layer0
-> Backend/Output_data/Layer0
-> Backend/Navigation/Core/layer1
-> Backend/Output_data/Layer1
-> Backend/Benchmark consumers
```

## Notes

- Layer1 now uses one canonical history table as its source of truth.
- Layer0 and its Firebase adapter now live under `Backend/Navigation/Core`, not a
  separate `Services` package.
- Sensor-specific `sht30/*` and `npk/*` artifacts under
  `Output_data/Layer1` are compatibility outputs derived from canonical
  rows, not independent processing pipelines.
- The former `layer2/` feature builders had no importers and were removed.

## Risks

- Changing Core outputs can affect `Benchmark` and `Frontend` consumers.
- Deleting compatibility outputs before migrating consumers will break
  downstream pipelines.
