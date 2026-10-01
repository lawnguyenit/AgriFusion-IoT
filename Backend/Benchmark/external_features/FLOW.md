# External Feature Processing Flow

```mermaid
flowchart TD
    A["Intake canonical + manifest + artifact hashes"] --> B["Verify intake / raw provenance"]
    B --> C{"Resolve profile by dataset_id"}
    C -->|"UCI"| U["8 observed sensor/context columns"]
    C -->|"Stuard"| S["6 strict soil/environment columns; omit target moisture"]
    U --> D["Apply feature allowlist; exclude criterion.*"]
    S --> D2["Strict sensor-only group; omit moisture descendants, meter, battery, regime, IDs"]
    D2 --> CTX["Separate optional irrigation-context contrast"]
    D --> E["Apply dataset time scope: timestamp < 2005-03-01"]
    D2 --> F["Use all valid canonical soil anchors"]
    E --> G["Sort by timestamp; require unique time key"]
    F --> G2["Sort within entity_id; require unique entity/time"]
    G --> H["Values group: current observation per sample_id"]
    G2 --> H
    CTX --> H
    H --> I["Explicit numeric coercion + parse/nonfinite/missingness audit"]
    I --> W["Trailing windows: default 3h and 8h"]
    W --> J["Per measurement: mean, std, min, max, count"]
    J --> K["Closed-both causal window: current + prior rows; min 2 values"]
    K --> L["Feature superset + group registry + missingness audit"]
    B --> M["Carry raw / intake / canonical hashes and run IDs"]
    M --> L
    L --> N["Separate pre-train handoff keyed by sample_id"]
```

## Feature construction detail

```mermaid
sequenceDiagram
    participant I as Intake canonical
    participant P as Dataset profile
    participant W as Window builder
    participant R as Feature registry
    participant A as Pre-train audit
    I->>P: dataset_id + timestamp/entity/value schema
    P->>W: time keys, allowed measurements, scope, groups
    W->>W: filter scope; stable-sort; reject duplicate time keys
    W->>W: emit values group keyed by sample_id
    loop Each requested horizon (default 3h, 8h)
      W->>W: trailing [t-horizon, t], grouped by entity
      W->>W: compute mean/std/min/max/count; require at least 2 values
    end
    W->>R: superset, feature groups, per-column missingness
    R->>A: registry + source lineage + stable sample keys
```

## Source routing

- Stuard groups histories by irrigation line. The target source
  `soil_moisture_pct` and all descendants are excluded from predictive groups.
  Strict `values` and trailing-window groups contain the other six
  soil/environment measurements. Battery, cadence, line/regime, and IDs remain
  outside X. The optional `irrigation_context` group separately stores causal
  meter increments and meter alignment age as an operational proxy contrast.
- UCI uses a source-code measurement allowlist. Analyzer `(GT)` reference
  measurements define CO/NOx targets and remain excluded from learner-visible
  X. The canonical `criterion.*` namespace is retained for compatibility;
  `criterion_only` is a leakage-exclusion role, not an independent-criterion
  claim.
- UCI feature runs apply the documented source period, timestamps strictly
  before 2005-03-01. The canonical intake remains unchanged; the manifest and
  registry record included and excluded row counts and the original endpoint.
- Intake manifests and canonical artifacts are verified against their
  artifact catalog; the raw release manifest hash is also checked and carried
  into the feature registry for pre-train lineage.
- The default output is one wide `feature_superset.parquet`, not one file per
  feature recipe. `feature_group_registry.json` lists only groups present for
  that dataset. UCI has `values` and causal windows; Stuard additionally has
  `irrigation_context`, which can be selected as a separate operational-proxy
  contrast without recalculating sensor features.

The engine rejects duplicate timestamps within an entity because row order
cannot define a causal ordering among equal-time observations. It records the
original canonical row position and includes the current and prior observations
inside each trailing horizon. Missing warm-up statistics stay null. These are
elapsed-time windows, not fixed row-count lookbacks; the manifest records
horizons and minimum count so changes produce a new versioned run. Every
allowlisted current measurement is explicitly converted with
`to_numeric(errors='coerce')` before it is written or used in a window. The
feature-quality artifact records the original dtype, numeric dtype, missing
count, parse failures, and nonfinite values; infinities become missing. The
immutable canonical artifact retains the original source representation.

## Where to change feature processing

| Desired change | Current owner |
|---|---|
| Add a dataset or set its timestamp/entity/measurement allowlist and scope | [profiles.py](profiles.py) |
| Change default horizons or minimum observations | `contracts.py`; explicit CLI overrides are in [main.py](main.py) |
| Change window statistics, causal boundaries, or grouping | [windowing.py](windowing.py) |
| Change persisted groups, manifest, or lineage fields | `persistence.py` |

The window builder only reads columns in the feature profile. Changing a label
target source does not automatically add that source to X.
