# Phase C — Artifact map

| Artifact family | Vai trò |
|---|---|
| `tasks/point/` | Point label authority |
| `tasks/temporal/` | Temporal label authority |
| `tasks/same_y/` | Source-label transfer projection |
| `audit/rule_firings` | Rule-level evidence lineage |
| `audit/resolutions` | Resolver decisions |
| `audit/assignments` | Assignment provenance |
| `run_metadata/label_release_manifest.json` | Release authority và hashes |

Các artifact trong `tasks/` phải được materialize từ Assignment, không tạo lại
label ở Evaluation.
