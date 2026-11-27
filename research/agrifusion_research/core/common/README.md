# core/common

Leaf utilities shared by every research lane (imports only `agrifusion.settings`).

| Module | Provides |
|--------|----------|
| `paths.py` | `REPO_ROOT`, `RESEARCH_OUTPUT_ROOT` (`output/research`), `<LANE>_ROOT`, `lane_output_root()` |
| `digests.py` | every hash helper: `file_sha256`, `bytes_sha256`; normalized family (`stable_digest`, `dataframe_digest`, ...); raw family (`stable_hash_object`, `hash_dataframe_rows`, `dataframe_schema_hash`). The two families give different values for floats/None; keep the one a caller already uses. |
| `artifacts.py` | `create_run_directory`, `utc_run_id`, `write_json`, `write_yaml`, `write_text` |
| `run_inputs.py` | YAML run-input files (`--inputs`) validated into `RunInputs`; `parse_with_run_inputs` |
| `provenance.py` | `resolve_code_commit(repo_root)` |

Merged from the former `common/` and `shared/` packages in GD5; the legacy label/split
helpers that had no importer were deleted (see git history before commit s5b).
