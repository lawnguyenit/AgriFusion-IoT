# B2 review decision

The selection profile answers **which synchronized fold candidate** is being tested:

```text
Q×K matrix / E1_PRIMARY_7D_V1
or
Q×K matrix / E1_DIAGNOSTIC_5D_V1
```

The same Q×K matrix must use one fold policy per profile. The fold comparison
report is diagnostic; it does not move boundaries or select a primary silently.

The review decision answers **whether the candidate is scientifically usable**:

- ontology and resolver policy;
- task-specific support thresholds;
- approved derived-evidence, continuity and window contracts;
- precommitted differential contract and E3 claim.

The generated template is intentionally `PENDING_REVIEW`. B2 rejects it until
the reviewer changes it to `APPROVED` and fills every required field. B2 does
not infer missing thresholds, move fold boundaries, or apply a default window.

Support is checked separately:

- Point: eligible class counts;
- Temporal: eligible class counts, event counts and cluster counts;
- Same-Y: transfer class counts and cluster/anchor support; event count is not
  required because Same-Y is a label-transfer projection.
