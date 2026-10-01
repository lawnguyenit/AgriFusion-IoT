# External support gate

This audit applies the user-approved mapping of B2 profile
`SUPPORT_PROFILE_OBSERVED_MIN_7D_V1`'s TEMPORAL support floors to external
candidate targets: at least 20 rows in each class, 5 persistent events, and 5
distinct persistent episode clusters in each of train, validation, and test.
An episode cluster is keyed by entity and contiguous persistent-label episode.

Every q/τ/threshold-scope candidate is reported. A candidate passes only when
all three partitions pass. This is a target-support gate, not model approval;
pre-train feature leakage, split integrity, and other audit gates still apply.
This aggregate support result is **B2-A**. The companion
`candidate_entity_estimability.csv` is **B2-E**: it reports the fraction of
entities with both known classes per partition as PASS/PARTIAL/FAIL. B2-E is
interpretive evidence and does not block an aggregate diagnostic fit; it must
not be conflated with B2-A. Single-series datasets have no entity-conditioned
B2-E result.

For q/τ sensitivity comparisons without an approved minimum-event gate, run
`grid_main`. It reports known, unknown, positive and negative support,
prevalence and persistent-event counts per temporal partition without applying
pass/fail thresholds.
