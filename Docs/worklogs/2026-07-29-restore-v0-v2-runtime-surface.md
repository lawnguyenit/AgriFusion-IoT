## Task Objective

Restore the runtime-surface cleanup that removes active `v3`, `v5`, and `v6`
family execution from `Backend/Benchmark/dataset_views` and
`Backend/Benchmark/weak_labels` on top of the current `main` state, without
changing the intended `v0`/`v1`/`v2` semantics.

## User Intent

Recover the previously implemented cleanup that was pushed on side branches but
did not land cleanly on `main`, so the user can push a corrected version again.

## Current Behavior

`main` currently still exposes `v3` and `v6` families in `dataset_views`,
retains blocked `v5` registrations, and still builds `v6` artifacts in
`weak_labels`. The runtime therefore still carries removed family surfaces and
can re-trigger import/runtime failures when those paths are touched.

## Confirmed Facts

- `main` is clean and matches `origin/main`.
- Commit `858b2d5` contains the prior `weak_labels` cleanup.
- Commit `c1a7b23` contains the prior `dataset_views` cleanup.
- Neither cleanup commit is currently an ancestor of `main`.
- Current `main` still imports and materializes removed family code.

## Unresolved Questions

- Whether the prior cleanup commits cherry-pick cleanly onto the current
  `main` state.
- Whether any post-cleanup `main` changes need to be preserved while restoring
  the reduced runtime surface.

## Assumptions

- The desired runtime surface is `v0` / `v1` / `v2` only.
- Reinstating the prior cleanup behavior is preferable to preserving dormant
  `v3` / `v5` / `v6` code paths.

## Affected Modules and Files

- `Backend/Benchmark/dataset_views/*`
- `Backend/Benchmark/weak_labels/*`
- `Backend/tests/*` if validation or compatibility adjustments are required
- `Backend/Benchmark/dataset_views/README.md`
- `Backend/Benchmark/dataset_views/FLOW.md`
- `Backend/Benchmark/weak_labels/README.md`
- `Backend/Benchmark/weak_labels/FLOW.md`

## Implementation Plan

1. Reconstruct the cleanup from the preserved branch commits.
2. Resolve any drift against current `main`.
3. Validate runtime entry points and compilation for `dataset_views` and
   `weak_labels`.
4. Update docs/flow files to match the restored active runtime surface.

## Architectural Decisions

- Restore the reduced active runtime surface instead of maintaining blocked but
  importable legacy family code.
- Treat `v3` / `v5` / `v6` removal as a runtime-surface correction, not as a
  semantic relabeling change for active `v0` / `v1` / `v2`.

## Progress Status

Implemented and validated on a dedicated restore branch.

## Validation Commands and Results

- `python -m compileall Backend\Benchmark\dataset_views Backend\Benchmark\weak_labels`
  - Passed after the contract export cleanup.
- `python Backend\Benchmark\weak_labels\main.py`
  - Passed.
  - Produced run `weak_labels_20260729_234929`.
  - Confirmed no `v6` artifact group exists in the new run output.
- `python Backend\Benchmark\dataset_views\main.py`
  - Passed.
- `python Backend\Benchmark\dataset_views\main.py --views v2`
  - Passed.
  - Resolved to all four public V2 subviews.
- `python Backend\Benchmark\dataset_views\main.py --views v3`
  - Failed intentionally with: removed from active benchmark surface.
- `python -m unittest Backend.tests.test_dataset_views_selection Backend.tests.test_dataset_views_materialization Backend.tests.test_weak_labels_point_and_v2`
  - Passed: 14 tests.

## Compatibility Impact

Expected behavioral change: `v3`, `v5`, and `v6` should no longer be part of
the active runtime surface for `dataset_views` / `weak_labels`.

Confirmed preserved behavior:

- `dataset_views` keeps current `main` semantics for `v0` and `v1`
  feature membership.
- `dataset_views` retains the shared artifact/report contract needed by
  existing materialization tests.
- `weak_labels` retains tranche-0 provenance layout while removing V6
  generation.

## Remaining Risks and Follow-up Work

- Historical artifact directories from earlier runs still contain old
  `v6` folders because they are past outputs, not regenerated runtime
  state.
- `Backend\Benchmark\weak_labels\reporting\tranche0_contracts.py`
  still emits a pandas `FutureWarning` during concatenation; this did
  not block the restore task but remains worth a later cleanup.
