# Reference evaluation local — implemented and tested; full Drive sync pending

## Task Objective
Install and execute the supplied additive reference_evaluation study locally, preserve older lanes/evidence, and deliver inspectable checkpoints.

## User Intent
User approved C0–C4 with “thôi vậy triển khai local đi” on 2026-11-01. This authorizes the dedicated environment, official downloads, locked preflight/main study and result synchronization. No authorization to change scientific settings, production firmware/Core, historical labels/splits, or publish the private V9 manuscript.

## Current Behavior
The lane is installed at Backend/Benchmark/reference_evaluation. Execution root remains D:/Project/AgriFusion-IoT on codex/wade-v9-publication; execution HEAD was69fd0e2 and source bytes are separately frozen. A safe backup worktree/branch codex/reference-evaluation-local-20261101 starts at public b194b39, excluding private V9 ancestry. Source milestone46bd89f and preflight record5966f8e were pushed normally. The main launcher completed exit0; current report is Backend/Output_data/reference_evaluation/report/current_graph__71b84c1ff33cc2a3. Complete local export is Backend/Output_data/reference_evaluation/drive_sync.

## Confirmed Facts
- Installer --check/install passed:36 lane files and16 fixture inputs created; canonical existing worklog preserved. Installed lane hashes match payload. Original package remains unchanged.
- Dedicated Python3.12.12, NumPy2.3.5, pandas2.2.3, sklearn1.8.0, SciPy1.17.0, joblib1.5.3 installed under ignored output-root _venv; pip check passed. Conda base was not modified. Actual transitive versions are recorded.
- Official Beijing raw:420768 canonical rows, adequate_for_declared_scope; scored train/development/selection/assessment=221516/51868/41362/45421. Appliances:3290 canonical rows, limited_support; corresponding scored counts1950/469/387/387. Both hard gates pass. Complete-label training positives after masking are only5/6/6 for Appliances, so support limitations remain material.
- Preflight exit0:28 correctness tests,0 failures/errors/skips,0 HGB/logistic fits in correctness suite. Full P2 true. Legacy no-refit fixture counts at R0..3 are5/4/1/0;20 legacy MILP solves:14 optimal,6 time-limited, all returned witnesses valid and optimal values match DP. Four actual supervised toy fits passed separately.
- Main exit0 and full_plan_complete=true:6 fit units=24 supervised fits,126 evaluation units,3780 R0 pair rows,126 sensitivity units,16 generic solver units,1 final report. Main solver statuses:10 optimal and6 time-limited. Timeouts were retained, not recast as optima.
- Active graph has279 nodes:2 audit+1 validate+1 smoke+6 fit+126 evaluate+126 sensitivity+16 solver+1 report. Historical preflight report remains as immutable evidence outside the active report pointer.
- Independent persisted-output validation passed:5319 READY-declared file hashes/sizes,8 selected NPZ contract checks, cohort/interval/R0 orientation/nesting/truth containment and solver checks; errors=[]; no refit/tuning was performed by this checker.
- Original tracked-file hash comparison found only PROJECT_MAP.md and PROJECT_STATUS.md changed by this task. Original application/firmware/Core bytes remain unchanged; new lane is additive.
- Actual Windows code fingerprint:2f435e0dfcbe8220aac9d0f2db0ac9c7965669159dbdcaa78dfef6b2f69ef067; config868261e939b028c17c33f319d78a178f5261edb76ba4002b2f4251421c2e6fec; environment4e755ea143367f356117cdfaf77a0ced45df08a042c856db447a357acf0e0f0b. Use the recorded inventory, not Git commit alone, as executed-source authority.

## Unresolved Questions
Full main delivery to Drive is not verified. Connector returned429 upload_protection_limit_exceeded, explicitly requesting retry in3 hours. Edge CDP Emulation.setFocusEmulationEnabled timed out twice; native Edge accessibility was unavailable. No app input, authentication change or sharing change was performed. Local execution is complete; remote delivery is partial. Scientific adequacy remains limited for Appliances; no physical/novel-method/future-ranking claim follows from plan completion.

## Assumptions
Scientific settings remain the delivered locked config. All masks/sites/seeds are dependent study conditions, not independent datasets. Output-root venv/cache/raw archives are not included in delivery. Documentation config.status retains its original delivery-origin wording; actual execution status is in manifests/current graph/report.

## Affected Modules and Files
- Installed36 files under Backend/Benchmark/reference_evaluation: contracts/config/targets; sources/preparation; features/Markov/fitting; evaluation/bounds/decisions/audit/sensitivity/solver; CLI/pipeline/stages/storage/reporting; tests and README/FLOW. No application-code repairs were required.
- Output root Backend/Output_data/reference_evaluation owns new raw releases, fixtures, venv, unit evidence, source snapshots, invocation/launch receipts, graph/indexes and export.
- PROJECT_MAP.md, PROJECT_STATUS.md and this canonical worklog own current state. Historical RUN_INDEX.csv at repository root remains the old handoff census; the new lane has its own live RUN_INDEX.csv.
- D:/Project/reference-evaluation-ops-20261101 contains operational monitors, transport adapters, independent checker, baseline hashes and delivery receipts. These are outside the scientific source snapshot.
- Drive target: https://drive.google.com/drive/folders/1jZq5t9gNNe_W1Tk8V9mtALmWpq885lNM.448 transport objects have verified metadata/size; this is not complete coverage of the final study.229 attempted objects failed with upload throttling; additional units finished afterward. See drive_delivery_partial_final.json for exact IDs and failed attempted paths.

## Implementation Plan
C0 installation/environment:complete. C1 full audit/validate/smoke:complete. C2 preflight delivery:verified with lossless connector transport exceptions. C3 locked main:complete. C4 independent local validation:complete; final packaging/documentation/Git checkpoint finalized in this task. Full remote main sync remains blocked by connector quota and unavailable browser control. Resume only missing/changed deliveries using recorded IDs/hashes once access is available; do not rerun training merely to retry upload.

## Architectural Decisions
Dependency direction is CLI→orchestration→separate source/preparation/model/evaluator/solver owners, with numerical contracts/math separated from storage and reporting. Evaluator objects omit full truth; selection is frozen before downstream truth audit. END uses three preceding positive recorded-hour states followed by current0, train/entity q75, splits60/15/12.5/12.5, six fixed candidates, train seeds11/22/33, one job/two threads and a single global source/partition R budget. Scientific settings and existing persistent formats are unchanged (csv_npz_v1).

Delivery adapters do not alter original READY bytes: connector100MiB/file and zero-byte rejection required gzip for two audit CSVs and an empty-file ZIP with original hashes. Main per-file metadata traffic was too slow, so complete units were bundled as ARTIFACTS.zip+SUMMARY, preserving/restoring paths through MAIN_TRANSPORT_MANIFEST. Some earlier loose objects coexist remotely; they are not an independent authority. The final local export preserves the original uncompressed source-defined tree and is authoritative for the full study.

## Progress Status
Approved and implemented locally. Preflight/full study tested and local checkpoint independently verified. User acceptance pending. Full Drive main delivery blocked; do not report it as complete. No production deployment, firmware flash, Firebase write or historical model refit occurred.

## Validation Commands and Results
- INSTALL_LOCAL.py --repo D:/Project/AgriFusion-IoT --check, then install:exit0,52 creates, worklog preserved. Installed-byte verification36/36 passed; CLI --help passed.
- uv python install3.12 installed3.12.12; dedicated venv dependencies installed; pip check passed.
- monitor_launch.py preflight --install-deps --download invoked the delivered RUN_LOCAL.py with actual3.12 executable:exit0,489.7985s including environment setup; full P2 and smoke verified.
- monitor_launch.py all:exit0,3855.0876s (64m15s). Maximum2-second sampled process-tree RSS sum857456640 bytes (~818MiB). Shared pages can be double-counted; this is not a continuous global physical-memory peak. Preflight sampled max508039168 bytes.
- check_checkpoint.py initially had a Path subscripting typo in the external checker, corrected without changing any study code/artifact. Recheck exit0:5319 files,3780 pair rows,8 NPZ samples, no errors; checkpoint_validation.json records details.
- Original tracked hashes compared:only the two intended project documentation files changed. No broader regressions were required because shared contracts/old application code were not modified.
- Connector uploads verified per object by metadata byte-size readback; original/transport hashes are recorded locally. No remote re-download hash assertion is made.429 quota failures and two Edge timeouts are retained as delivery limitations.

## Compatibility Impact
Additive lane only; old source/data/schemas retained. Historical incomplete provenance remains unknown. Exact command, source/config/input/environment signatures and READY hashes accompany the new runs. Lane README/FLOW/source/config were not edited during execution. Backup commits use a separate worktree so execution Git metadata remains stable. Cross-platform consumers must normalize Windows relative path separators; archive member paths use POSIX separators.

## Remaining Risks and Follow-up Work
- Complete missing Drive delivery after upload access recovers, or upload the complete local export directly in Drive; never claim current partial remote tree is the final checkpoint.
- Appliances remains limited_support, including very few positive complete training labels. Full-plan completion does not override this caveat.
- Resume across a changed execution Git HEAD is not certified by this run: storage writes code_snapshots/<code_sha>/SNAPSHOT.json with Git metadata; an otherwise identical source inventory may produce different snapshot metadata after a commit and conflict with immutable exported bytes. Keep the current execution checkout stable for exact resumes; review/fix that metadata transition with a focused regression before relying on it. No such transition occurred here.
- User review/acceptance and any paper/public-release decision remain separate. No rerun, target tuning or scientific scope expansion is required to retry delivery.

## Final Local Package
Complete native export/package verified: reference-evaluation-20261101-complete.zip,115006856 bytes,5686 files, SHA256 c349540b7ba25f7f9884d8fe436d06a2c3a5993cdd947e9f4285432eb6cec16a. Native export hashes and ZIP CRC pass. Two lossless80MiB-or-smaller parts plus DELIVERY_PARTS.json are prepared for the connector100MiB limit; upload remains blocked by quota. No automatic future retry is scheduled.
