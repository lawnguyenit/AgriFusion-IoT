# External timestamp-block split flow

```mermaid
flowchart LR
    A["Canonical sample_id + anchor/source timestamps"] --> B["Validate unique IDs and valid timestamps"]
    B --> C["Union rows sharing anchor, environment, or meter timestamp keys"]
    C --> D["Sort linked timestamp blocks; first 70% / next 15% / final 15%"]
    D --> E["Map every linked row to the same partition"]
    E --> F["Persist split parquet + source hash + boundaries + report"]
    F --> G["Pre-train audit joins labels and selected feature groups by sample_id"]
```

Current output is one forward chronological holdout, not repeated rolling
folds. No sample is shuffled and shared anchor/environment/meter timestamps
cannot cross partitions.
This lane does not establish target support or freeze an external task.
