# System architecture

AgriFusion-IoT has two connected processing lanes and one presentation
surface. The lanes share data contracts, but they do not share ownership of
the same artifacts.

```text
IoT node / Firebase RTDB / JSON export
                |
                v
Backend Layer0: immutable source evidence and sync state
                |
                v
Backend Layer1: canonical telemetry history and field governance
                |
        +-------+--------+
        |                |
        v                v
Operational consumers   Research benchmark lane
                         dataset_views
                         -> weak_labels
                         -> protocol_registry
                         -> evaluation_protocols
                         -> validity_lifecycle
                         -> model_suite

Frontend/public reads the separate Firebase `result/*` presentation
contract. It is currently a demo-first dashboard; it is not a direct
viewer of Layer1 files.
```

## Operational telemetry lane

### Edge

`IoT_Node/src/main.cpp` delegates to `IoT_Node/lib/AppEntry`. The current
production path is `AppEntry -> AppRuntime`, which coordinates sensor
collection, transport readiness, buffering/replay and RTDB publication.

The current firmware configuration targets Node2 and publishes canonical
telemetry under:

- `/Node2/telemetry/<date>/<event>` — dated telemetry records;
- `/Node2/latest/current` — newest snapshot;
- `/Node2/latest/meta` — polling metadata for backend synchronization.

Diagnostic paths under `/debug/Node2` are disabled by default and must not be
treated as the production source of truth.

### Backend

- `Backend/Navigation/Core/layer0` loads Firebase or JSON-export input and
  stores auditable raw artifacts under `Backend/Output_data/Layer0`.
- `Backend/Navigation/Core/layer1` converts source records into the canonical
  history contract and writes reports, quality views and compatibility outputs
  under `Backend/Output_data/Layer1`.
- `Backend/Config` owns runtime settings, environment loading, paths and
  storage helpers.

The backend accepts a logical `--node-id`; it is not hard-coded to Node2.
When reading the firmware described above, configure the backend with the
matching node id instead of relying on the default.

## Research benchmark lane

The benchmark lane starts from frozen Layer1 canonical artifacts. Its owners
are:

| Lane | Owns | Does not own |
| --- | --- | --- |
| `dataset_views` | feature-view materialization | labels or model training |
| `weak_labels` | evidence, weak-label authority and provenance | raw telemetry mutation |
| `protocol_registry` | protocol/environment authority | downstream model fitting |
| `evaluation_protocols` | folds, domains and runner manifests | changing source labels in place |
| `validity_lifecycle` | readiness and lifecycle audits | creating an unrelated split |
| `model_suite` | model execution, metrics and reports | redefining the benchmark contract |

The handoff is file-based and versioned. The central contract is described in
[Benchmark to Model Suite](../Backend/Benchmark/BENCHMARK_TO_MODEL_SUITE_SPEC.md).

## Frontend surface

`Frontend/public` consumes `result/*` from Firebase when configured for live
mode, and otherwise renders a deterministic demo payload. The current
tracked backend does not publish that `result/*` contract, so the dashboard
must not be described as the automatic output of `Backend/main.py` until a
publisher is implemented and verified.
