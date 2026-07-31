# Native Semantic Label Engine — Phase C

This lane implements only a complete, reviewed Phase B semantic contract.
It is E1-sensitive by authorization, keeps intrinsic assignments separate from
feature/fold admissibility, and never modifies the legacy weak-label engine.

The engine fails closed unless the semantic contract contains the operational,
derived-evidence, compatibility, continuity, and complete window registries.
The default legacy `weak_labels` entrypoint remains unchanged.

Example invocation:

```powershell
python Backend\Benchmark\weak_labels\native_engine\main.py `
  --semantic-contract-run-dir <frozen-contract-run> `
  --protocol-registry-run-dir <frozen-registry-run> `
  --canonical-history <canonical-history.csv> `
  --canonical-evidence-schema <canonical-evidence-schema.csv> `
  --sensor-dependency-registry <sensor-dependency-registry.csv> `
  --segment-manifest <segment-manifest.json> `
  --expected-difference-contract <expected-difference-contract.csv> `
  --output-root Backend\Benchmark\weak_labels\native_engine\artifacts
```

Native output uses task-oriented paths (`point`, `same_y`, and
`temporal_anchor`). Same-Y artifacts are transfer projections, not a new
semantic ontology. Feature-view admissibility and train-ready release remain
Phase D responsibilities.

