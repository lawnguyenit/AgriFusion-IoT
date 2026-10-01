# External support audit flow

```mermaid
flowchart LR
    A["Candidate labels + registry"] --> C["Join split rows by sample_id"]
    B["Temporal split"] --> C
    C --> D["B2-A aggregate support by candidate × partition"]
    C --> E["Per-entity support table"]
    D --> F{"Approved profile?"}
    F -->|"B2 TEMPORAL mapping"| G["Apply class / event / episode floors"]
    F -->|"No gate registered, e.g. UCI grid"| H["Report descriptive counts only"]
    G --> I["B2-A aggregate gate summary"]
    E --> K["Entity discrimination: both classes present?"]
    E --> K2["Per-entity support adequacy: class + event + episode floors"]
    K --> L["Claim interpretation only; does not block aggregate fit"]
    K2 --> L
    H --> J["Partition support CSV; no pass/fail promotion"]
```

**B2-A** checks at least 20 rows per class, five persistent events, and five
distinct entity-specific episode clusters in each partition. The
`candidate_entity_support.csv` reports two independent properties per entity
and partition: mathematical discrimination estimability (both classes are
present) and support adequacy (at least 20 rows per class, five persistent
events, and five distinct positive episode clusters). The
`candidate_entity_estimability.csv` summary reports counts and statuses for
both. A line may therefore be mathematically estimable while still lacking
enough evidence for a within-line claim. Neither status blocks an aggregate
diagnostic fit. The v1 `entity_claim_estimability_status` field remains as a
compatibility alias for mathematical two-class estimability; consumers should
use `entity_support_adequacy_status` when interpreting evidence sufficiency.
Single-series datasets report both entity layers as not applicable when no
entity dimension exists.

`grid_main` uses the same keyed support summary shape for candidates without a
registered gate. It reports q/τ class counts, unknowns, prevalence, and event
counts per partition, while recording `support_gate_applied=false`. In
particular, the UCI sensitivity grid must not inherit Stuard's B2 thresholds.

Neither path selects a target from model scores or trains a model. The output
is an auditable support input for the pre-train audit and target review.
