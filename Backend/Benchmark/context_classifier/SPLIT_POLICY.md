# Context Classifier Split Policy

## Purpose

This document defines how train, validation, and test splits are handled for the context-classifier benchmark.

The split contract is shared by both supported label schemes:

- `five_class_v1`
- `option2_4class`

The training pipeline already consumes these split-specific outputs directly, so this document describes the active protocol rather than a future plan.

## Canonical Rule

- Always sort by `timestamp`.
- Never mix the same local episode across train and evaluation.
- Prefer chronological evaluation over random row shuffling.

## Planned Split Regimes

### 1. Coverage-aware temporal split

Use when the dataset is a merged real+synthetic context timeline:

- split the real timeline first
- train: first 70%
- validation: next 15%
- test: final 15%
- then inject synthetic rows into `train` only
- keep `validation` and `test` as `real-only`
- search nearby temporal boundaries to retain more abnormal real rows in `validation` and `test`
- still enforce a purge gap between split boundaries

### 2. Plain chronological split with purge gap

Fallback mode when coverage-aware boundary search cannot improve class support:

- split the real timeline in strict time order
- apply the purge gap
- inject synthetic rows into `train` only

### 3. Episode-aware chronological split

Use when episode boundaries are available:

- keep each episode fully inside one split
- apply a purge gap between splits when needed

This is still a planned upgrade for real rows. Synthetic rows already carry episode metadata.

### 4. Real-only evaluation split

Recommended for thesis-grade reporting:

- training may mix `real` and `synthetic`
- validation/test should be filtered to `data_origin == "real"` when coverage is sufficient

## Current Limits

- The current builder emits the metadata needed for episode-aware and real-only evaluation.
- Real rows are still split primarily by chronological coverage-aware boundaries rather than explicit upstream episode ids.
- `option2_4class` improves validation/test coverage by merging `rain_humid_context` and `fertigation_spike` into `moisture_or_intervention_context`, but it does not create new real abnormal rows.
