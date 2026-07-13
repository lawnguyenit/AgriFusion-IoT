# Backend Services

## 1. Purpose

`Backend/Services` now keeps only the service layer required for accepted
pre-benchmark data acquisition.

At this stage, Services is limited to:

- shared infrastructure adapters
- Layer0 raw-ingestion orchestration and storage helpers

It does not own Layer1 canonical preprocessing, benchmark labeling, model
training, demo flows, or web-result publishing.

## 2. Active Structure

```text
Services/
|-- infrastructure/
|   `-- firebase_rtdb.py
`-- layer0_ingestion/
```

## 3. Naming Assessment

- `infrastructure/` is the clearest active name for shared technical
  components.
- `firebase_rtdb.py` is a normal concrete adapter name because it says
  exactly which external system it talks to.
- `layer0_ingestion/` is also a normal name because it maps directly to
  the accepted repository stage.

The earlier names that felt wrong, such as `telemetry_orchestrator`,
`telemetry_runtime_simulator`, `result_publisher`, and
`output_cutoff_maintenance`, were not nonsense names, but they belonged
to a broader demo/runtime/report architecture that is no longer the
current pre-benchmark focus. That mismatch is the main reason they felt
off.

## 4. Inputs

- `Backend/Services/.env`
- Firebase RTDB or JSON export
- CLI parameters from `Backend/main.py`

## 5. Outputs

- `Backend/Output_data/Layer0/**`
- Layer0 audit artifacts and sync state

## 6. Reproducibility

```powershell
copy Backend\Services\.env.example Backend\Services\.env
python Backend\main.py --help
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --full-history
python Backend\main.py --only-layer0 --source json-export --input-json C:\path\export.json --node-id Node1 --full-history
```

## 7. Notes

- Services now supports Layer0 only.
- Shared infrastructure now lives under `Backend/Services/infrastructure`.
- Layer1 lives in `Backend/Core/layer1`.
- Anything after Layer1 belongs to a later architectural phase and is not
  kept in Services during this cleanup.
