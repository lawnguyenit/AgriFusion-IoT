# Split Policy

## Purpose

This document defines who owns train/validation/test splitting for benchmark runs and what the current split semantics mean.

## Current Owner

The current split owner is the pretrain data pipeline:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\src\data\preprocessing.py`

The current split math was originally implemented in:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\src\data\splitting.py`

It is now being extracted into a dedicated split-policy module so that:
- split logic is versioned explicitly,
- pretrain and downstream share the same split contract,
- and evaluation can become stricter later without hiding split behavior in preprocessing code.

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

1. No purge gap between train and validation
2. No purge gap between validation and test
3. No episode-aware grouping
4. No block-by-day or block-by-event split
5. Validation and test can still be too close in temporal regime

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
- `chronological_with_gap`

Behavior:
- keep chronological order
- insert an explicit gap between:
  - train and validation
  - validation and test

### Stage 3

Add:
- `block_by_day`

Behavior:
- split by day blocks instead of raw contiguous row counts

### Stage 4

Add:
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
