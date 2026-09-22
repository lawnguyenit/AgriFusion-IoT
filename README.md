# AgriFusion-IoT

AgriFusion-IoT combines an agricultural IoT firmware, a canonical telemetry
pipeline, a research benchmark workspace and a static dashboard. The
production telemetry lane and the research lane are connected by explicit
artifacts; they are not one undifferentiated application.

## Start here

Read in this order:

1. [System architecture](public-docs/architecture.md)
2. [Repository hygiene](public-docs/repository-hygiene.md)
3. [Backend pipeline](Backend/README.md)
4. [Benchmark workspace](Backend/Benchmark/README.md)
5. [IoT Node firmware](IoT_Node/README.md)
6. [Frontend dashboard](Frontend/README.md)

## End-to-end map

```text
IoT Node / Firebase RTDB / JSON export
                |
                v
Backend/Navigation/Core/layer0
                |
                v
Backend/Output_data/Layer0
                |
                v
Backend/Navigation/Core/layer1
                |
                v
Backend/Output_data/Layer1/canonical
                |
        +-------+--------+
        |                |
        v                v
Operational use     Backend/Benchmark
                    dataset views -> weak labels -> protocols
                    -> lifecycle audits -> model suite

Frontend/public reads the separate Firebase result/* presentation contract.
```

## Backend quick start

From the repository root:

```powershell
python -m pip install -r Backend/requirements.txt
python -m Backend.main --help
```

Run Layer0 and Layer1 from Firebase or a JSON export:

```powershell
python -m Backend.main --source firebase --node-id Node2 --full-history
python -m Backend.main --source json-export --input-json C:\path\export.json --node-id Node2 --full-history
python -m Backend.main --only-layer1
```

The backend accepts `Node1`, `Node2` or another logical node id. Match the
value to the source path; the firmware currently publishes Node2 data, while
the backend default remains configurable through `EXPORT_NODE_ID`.

## Benchmark quick start

```powershell
python -m Backend.Benchmark.dataset_views.main --help
python -m Backend.Benchmark.evaluation_protocols.main --help
python -m Backend.Benchmark.model_suite.cli --help
```

Start with [Backend/PIPELINE_FLOW.md](Backend/PIPELINE_FLOW.md) and the
[benchmark handoff contract](Backend/Benchmark/BENCHMARK_TO_MODEL_SUITE_SPEC.md).

## Frontend quick start

```powershell
python -m http.server 4173 -d Frontend/public
```

The dashboard runs in safe demo mode by default. Live Firebase mode requires
a local `Frontend/public/config.local.json`; that file is intentionally not
tracked. The current backend canonical pipeline does not itself publish the
frontend `result/*` contract, so live dashboard integration is a separate
integration boundary and must not be inferred from Layer1 output alone.

## What is intentionally not in the source contract

- `Backend/Output_data/` and benchmark artifacts are generated outputs.
- `Secrets/`, `.env` files, Firebase local config and private firmware
  credentials are local-only.
- Physical sensor, SIM, Firebase-rule and deployment claims require explicit
  runtime evidence.
- Weak labels, benchmark targets and model predictions are research-derived
  artifacts, not observed sensor measurements.

For the tracked documentation map, see [`public-docs/README.md`](public-docs/README.md).
