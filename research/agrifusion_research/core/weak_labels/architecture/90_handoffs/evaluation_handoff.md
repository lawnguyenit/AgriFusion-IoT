# Handoff sang Evaluation

## Weak Labels cung cấp

```text
sample_id
task_id
horizon_id
label_name
label_status
intrinsic_eligibility
semantic_contract_hash
assignment provenance
```

## Dataset Views cung cấp

```text
feature view
feature schema
feature history
feature missingness
feature artifact hash
```

## Evaluation làm

```text
join sample_id
feature eligibility
fold/split/purge projection
matched cohort
train-ready manifest
```

Evaluation không được gọi lại Q/K, resolver hoặc label builder.

## Execution scope

Evaluation consumes an explicit execution profile for each run. The profile
declares the environments whose labels may be applied, used for training,
evaluated, and treated as a target.

The current RQ1 profile is E1-only:

```text
label_apply = [E1]
train = [E1]
evaluation = [E1]
target = []
```

Therefore the current handoff produces an E1 train-candidate manifest only;
it does not claim E2/E3 transport. RQ2A and RQ2B use separate profiles and
require native label releases covering their requested environments.
