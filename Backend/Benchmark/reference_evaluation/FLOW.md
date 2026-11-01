# Implemented reference-evaluation flow

| Stage | Inputs | Outputs and gate |
| --- | --- | --- |
| audit | Explicit local/official raw release, resolved config | Raw checksum/provenance, canonical CSV, four partitions, reference/dependency/support audits. No model fit. |
| validate | Unit suite and delivered legacy fixture | Independent oracle/DP checks, causality, parser, storage and integration checks; legacy 5/4/1/0 regression and MILP witnesses. unit-only does not pass full P2. |
| smoke | Synthetic train/development plus recorded early prefixes | Four tiny supervised local fits and input/forecast/bounds plumbing, never new-source efficacy. |
| fit | Audited train, permitted development, P2 + smoke gates | Six frozen candidates, parameters/models, development-only static default, exact fit signature. |
| evaluate | Frozen fit, selection/assessment observations and fixed mask | Public NPZ input contracts, 15 R0 pair intervals, point estimates, selected actions; truth joined downstream in audit-only outputs. |
| sensitivity | Fixed public inputs, global R grid | Primary-pair intervals and breakpoint brackets; specified archive-error corruption with conditional validity checks. |
| solver | Fixed selection inputs, specified cases | One checkpoint per direction/budget; optimal/timeout/error statuses, incumbent, dual bound, witness and runtime. |
| report | Current validated dependency graph | Readable tables and status, expected/completed case counts, fixed baselines and certificate summaries. |
| export | READY-declared artifacts, indexes, code/source provenance | Local incremental drive_sync tree and manifest. No automated Drive upload is asserted. |

The orchestration in pipeline.py calls separate numerical/source/storage owners.
No stage mutates production raw/canonical output or any frozen V9 artifact.
One pool error budget spans every eligible segment and site in a source/period.
Feature and target histories never cross an entity, true gap or partition.

Storage writes running -> complete/failed and records scientific support
separately. Completed bytes are checked before reuse. A changed parent removes
descendants from ACTIVE_GRAPH, while previous attempt directories remain.
The root readable indexes are operational entry points; per-run manifests and
READY checksums retain the provenance for every individual computation.
