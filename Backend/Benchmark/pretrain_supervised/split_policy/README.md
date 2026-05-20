# Split Policy Module

## Purpose

This module owns benchmark split strategy definitions.

Its job is to:
- define split strategies,
- create explicit split plans,
- and expose split metadata as artifacts instead of hiding split behavior inside preprocessing code.

## Current Strategy

- `chronological_with_lookback_gap`

Behavior:
- sort by `timestamp`
- infer a purge gap from feature lookback such as `3h`, `8h`, `24h`, `72h`, unless an explicit override is provided
- keep train, validation, and test chronological
- exclude rows inside purge gaps
- train 70 percent
- validation 15 percent
- test 15 percent

Legacy compatibility strategy still exists:
- `chronological_v1`

## Input

- cleaned row count
- split ratios
- strategy name

## Output

- `SplitPlan`
- split slices
- split counts
- split manifest dictionary for artifact export

## Command

This module is called by pretrain. It does not have a standalone CLI yet.

## Assumptions

- the dataframe has already been sorted by `timestamp`
- split ownership stays with benchmark pretrain unless a later benchmark protocol moves it higher

## Current Limits

- only `chronological_v1` is implemented
- no purge gap
- no block-by-day
- no episode-aware split yet
