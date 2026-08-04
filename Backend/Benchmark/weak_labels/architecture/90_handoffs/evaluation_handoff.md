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
