# Split Policy Module

## Purpose

This module owns reusable train/validation/test split strategies for benchmark runs.

Its job is to:

- define strategy names
- build explicit split plans
- expose split metadata as artifacts instead of hiding split logic inside preprocessing

## Current Strategies

- `chronological_with_lookback_gap`
  - current default
  - infers purge-gap minutes from feature lookback unless an override is provided
- `chronological_v1`
  - legacy compatibility strategy without the newer lookback-gap behavior

## Input

- ordered row count
- split ratios
- strategy name
- timestamps when the strategy needs explicit temporal gaps
- feature columns when auto gap inference is enabled

## Output

- `SplitPlan`
- split slices
- split counts
- split manifest payloads

## Command

This module is import-only. It currently has no standalone CLI.

## Assumptions

- rows are already sorted by `timestamp`
- split ownership still lives with the benchmark pipelines that call this module

## Current Limits

- no day-block split yet
- no episode-aware split yet
- gap inference only looks at feature names such as `3h`, `8h`, `24h`
