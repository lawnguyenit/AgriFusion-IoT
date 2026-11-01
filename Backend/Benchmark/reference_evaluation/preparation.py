"""Four-way temporal assignments, train-only rule and finite-reference segments."""
import json
import numpy as np
import pandas as pd
from .contracts import FailedSupport, HOUR_NS, PARTITIONS, Segment
from .targets import end_labels, assert_disjoint_keys


def prepare_frame(frame, config):
    d = frame.copy().sort_values(["entity", "timestamp"], kind="stable").reset_index(drop=True)
    if d.empty or d.sample_id.duplicated().any() or d.duplicated(["entity", "timestamp"]).any():
        raise FailedSupport("Empty/duplicate canonical keys")
    if d.entity.isna().any() or d.timestamp.isna().any():
        raise FailedSupport("Missing entity/time keys")
    times = np.sort(d.timestamp.unique())
    fractions = np.cumsum(config["splits"]["fractions_of_sorted_unique_source_times"])
    indexes = [int(np.floor(len(times)*f)) for f in fractions[:-1]]
    if len(set([0]+indexes+[len(times)])) != 5:
        raise FailedSupport("Insufficient unique times for four nonempty partitions")
    cuts = times[indexes]
    assignment = np.searchsorted(cuts, d.timestamp.to_numpy(), side="right")
    d["partition"] = np.asarray(PARTITIONS)[assignment]
    thresholds = {}; k = int(config["time_grid_and_target"]["K"])
    warmup = int(config["time_grid_and_target"]["warmup_per_segment"])
    quantile = config["time_grid_and_target"]["threshold"]["quantile"]
    for entity, group in d.groupby("entity", sort=True):
        train = group.loc[group.partition == "train", "value"].to_numpy(float)
        train = train[np.isfinite(train)]
        if not len(train):
            raise FailedSupport(f"No recorded train reference for entity {entity}")
        thresholds[str(entity)] = float(np.quantile(train, quantile))
    d["threshold"] = d.entity.map(thresholds)
    d["F"] = np.where(np.isfinite(d.value), (d.value > d.threshold).astype(int), -1).astype(np.int8)
    d["segment_id"] = ""; d["score"] = False; d["END_audit"] = -1
    segments = []; support = []
    for (entity, partition), group in d.groupby(["entity", "partition"], sort=False):
        positions = group.index.to_numpy(); current = []; groups = []
        previous_time = None
        for i in positions:
            t = int(d.at[i, "timestamp"])
            if d.at[i, "F"] < 0 or (current and t-previous_time != HOUR_NS):
                if current:
                    groups.append(current)
                current = []
            if d.at[i, "F"] >= 0:
                current.append(int(i))
            previous_time = t
        if current:
            groups.append(current)
        usable = short = positives = scored = 0
        for number, positions in enumerate(groups):
            sid = f"{entity}__{partition}__{number:06d}"
            states = d.loc[positions, "F"].to_numpy(np.int8)
            score = np.arange(len(positions)) >= warmup
            labels = end_labels(states, k)
            d.loc[positions, "segment_id"] = sid
            d.loc[positions, "score"] = score
            d.loc[positions, "END_audit"] = labels
            if not score.any():
                short += 1; continue
            segments.append(Segment(sid, str(entity), str(partition),
                                    d.loc[positions, "sample_id"].to_numpy(str),
                                    d.loc[positions, "value"].to_numpy(float), states, score))
            usable += 1; scored += int(score.sum()); positives += int(labels[score].sum())
        support.append({"entity": entity, "partition": partition, "canonical_rows": len(group),
                        "genuinely_missing_reference_rows": int((group.F < 0).sum()),
                        "continuous_segments": len(groups), "usable_segments": usable,
                        "short_segments": short, "scored_origins": scored,
                        "END_positives": positives, "END_negatives": scored-positives,
                        "positive_END_episodes": positives, "threshold": thresholds[str(entity)]})
    assert_disjoint_keys(segments)
    # Raw rows must not be reused across partitions, even by an aggregation.
    raw_owners = {}
    for partition, encoded in zip(d.partition, d.source_rows):
        for key in json.loads(encoded):
            if key in raw_owners and raw_owners[key] != partition:
                raise ValueError(f"Raw dependency crosses partitions: {key}")
            raw_owners[key] = partition
    totals = {part: sum(r["scored_origins"] for r in support if r["partition"] == part) for part in PARTITIONS}
    failures = []
    if min(totals.values()) <= 0:
        failures.append(f"No common scored cohort in one or more partitions: {totals}")
    train_parts = [end_labels(s.states, k)[s.score] for s in segments if s.partition == "train"]
    train_labels = np.concatenate(train_parts) if train_parts else np.array([], dtype=np.int8)
    if len(np.unique(train_labels)) != 2:
        failures.append("Recorded training reference has fewer than two END classes")
    limited = any(sum(r["END_positives"] for r in support if r["partition"] == part) < 10
                  for part in ("selection", "assessment"))
    metadata = {"partition_order": list(PARTITIONS), "cutpoints_recorded_ns": [int(v) for v in cuts],
                "thresholds": thresholds, "warmup": warmup, "K": k,
                "scored_origins_by_partition": totals, "raw_dependency_count": len(raw_owners),
                "raw_dependencies_cross_partitions": False, "segments_cross_entities": False,
                "hard_gate_passed": not failures, "hard_gate_failures": failures,
                "scientific_support_status": "failed_support" if failures else
                    ("limited_support" if limited else "adequate_for_declared_scope")}
    return d, segments, support, metadata


def segments_from_frame(frame, partition=None):
    d = frame if partition is None else frame.loc[frame.partition == partition]
    result = []
    for sid, group in d.loc[d.segment_id.fillna("") != ""].groupby("segment_id", sort=False):
        group = group.sort_values("timestamp", kind="stable")
        score = group.score.astype(str).str.lower().eq("true").to_numpy() if group.score.dtype == object else group.score.to_numpy(bool)
        if not score.any():
            continue
        result.append(Segment(str(sid), str(group.entity.iloc[0]), str(group.partition.iloc[0]),
                              group.sample_id.to_numpy(str), group.value.to_numpy(float),
                              group.F.to_numpy(np.int8), score))
    return result
