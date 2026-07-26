# Backend Data Pipelines

## 1. Purpose

`Backend/` currently covers the accepted pre-benchmark pipeline:

- Layer0 pulls raw telemetry into auditable local artifacts.
- Layer1 normalizes and flattens raw telemetry into canonical tabular
  outputs for downstream benchmark preparation.

Anything after Layer1 is not part of the active accepted path in this
cleanup pass.

## 2. Active Architecture

```text
Backend/main.py
    |
    +-- Config/
    |     `-- runtime settings, paths, IO helpers
    |
    +-- Core/
    |     +-- infrastructure/           -> Firebase RTDB access
    |     +-- layer0/                   -> raw ingestion into Layer0
    |     `-- layer1/                   -> canonical preprocessing
    |
    `-- Benchmark/
```

## 3. Main Stages

### Stage 1. Layer0 ingestion

- fetch source metadata
- decide whether current payload should be fetched
- persist raw history and sync state

### Stage 2. Layer1 preprocessing

- load Layer0 raw artifacts
- parse telemetry packets and context
- build canonical rows
- write canonical history, latest snapshot, debug views, and reports

## 4. Inputs

- `Backend/.env`
- Firebase RTDB or JSON export
- local artifacts in `Backend/Output_data`

## 5. Outputs

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Layer1/**`

## 6. Example Layer1 Output

```json
{
  "record.id": "Node1:2026-05-10:1778387046",
  "record.ts_server": 1778387046,
  "record.sample_time_local": "2026-05-10T11:24:06+07:00",
  "sht.temp_c": 35.09,
  "sht.humidity_pct": 69.09,
  "npk.soil_moisture_pct": 55.8
}
```

## 7. Reproducibility

Install backend dependencies:

```powershell
cd Backend
python -m pip install -r requirements.txt
```

Show supported commands:

```powershell
python main.py --help
```

Run Layer0 only:

```powershell
python main.py --only-layer0 --source firebase --node-id Node1
python main.py --only-layer0 --source firebase --node-id Node1 --full-history
```

Run Layer1 from existing local Layer0 artifacts:

```powershell
python main.py --only-layer1
```

Run Layer0 then Layer1:

```powershell
python main.py --to-layer layer1 --source firebase --node-id Node1 --full-history
```

## 8. Notes

- Layer0 is responsible for pull integrity and raw evidence.
- Layer1 is responsible for canonical flattening and tabular preparation.
- Benchmark-specific labeling and training logic belongs under
  `Backend/Benchmark`.

## 9. Detailed Flow Docs

For implemented control flow rather than folder scope summaries, read:

- [Backend Pipeline Flow](PIPELINE_FLOW.md)
- [Layer0 Flow](Navigation/Core/layer0/FLOW.md)
- [Layer1 Flow](Navigation/Core/layer1/FLOW.md)
- [Dataset Views Flow](Benchmark/dataset_views/FLOW.md)
- [Weak Labels Flow](Benchmark/weak_labels/FLOW.md)
- [Evaluation Protocols Flow](Benchmark/evaluation_protocols/FLOW.md)
- [Validity Lifecycle Flow](Benchmark/validity_lifecycle/FLOW.md)
- [Model Suite Flow](Benchmark/model_suite/FLOW.md)
