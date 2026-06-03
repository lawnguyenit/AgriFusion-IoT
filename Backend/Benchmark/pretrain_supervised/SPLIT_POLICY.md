# Split Policy

## Purpose

This document defines who owns train/validation/test splitting for benchmark runs and what the current split semantics mean.

## Current Owner

The reusable split owner is now:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\split_policy`

The current benchmark pipelines call this module rather than re-implementing split math locally.

## Current Strategy

Current default strategy name:

- `chronological_with_lookback_gap`

Current behavior:

1. sort rows by `timestamp`
2. infer the maximum lookback horizon from feature columns unless an explicit gap override is provided
3. keep rows chronological
4. insert purge gaps before validation and test
5. assign:
   - first 70 percent -> train
   - next 15 percent -> validation
   - last 15 percent -> test
6. mark rows inside the purge gap as excluded from train/validation/test

This strategy is more fair than the old contiguous split, but still not the final strict evaluation protocol.

## What It Does Well

- easy to reproduce
- stable across runs
- simple to debug
- good enough for early benchmark exploration

## Current Weaknesses

1. The gap is based on lookback horizon, not on explicit event episodes.
2. There is still no day-block or block-by-event split.
3. Validation and test can still be close in temporal regime even when a purge gap exists.
4. Gap inference depends on feature naming conventions such as `3h`, `8h`, `24h`.

## Current Contract

Pretrain creates the split once.
Downstream `v1` and `v2` reuse it.

That means if the split policy is weak, all downstream metrics inherit that weakness.

## Recommended Split Evolution

### Stage 1

Current implementation:
- `chronological_with_lookback_gap`

Behavior:
- use a gap derived from feature lookback such as `8h`, `24h`, or an explicit override
- exclude gap rows from supervised and pretrain splits

### Stage 1 legacy compatibility

Keep:
- `chronological_v1`

Reason:
- preserve comparability with current benchmark runs

### Stage 2

Add:
- `block_by_day`

Behavior:
- split by day blocks instead of raw contiguous row counts

### Stage 3

- `episode_aware`

Behavior:
- group rows from the same event episode into the same split
- prevent one event from being fragmented across train/validation/test

## Required Artifacts

Every pretrain run should eventually expose split artifacts clearly.

At minimum:
- `split_manifest.json`

Recommended later:
- `train_timestamps.csv`
- `validation_timestamps.csv`
- `test_timestamps.csv`

## Promotion Rule

Do not promote a model/schema comparison as a serious benchmark result unless the split policy used by that run is explicitly recorded in artifacts and reports.
