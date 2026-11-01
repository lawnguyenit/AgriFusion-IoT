"""Seeded mask generators; truth is allowed here only to simulate MNAR."""
import hashlib
import json
import math
import numpy as np


def stable_seed(*parts):
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def generate_mask(states, policy, seed, warmup=24):
    z = np.asarray(states, dtype=np.int8)
    if not np.isin(z, [0, 1]).all():
        raise ValueError("Mask generation requires the recorded binary fixture")
    rng = np.random.default_rng(seed)
    m = np.zeros(len(z), dtype=bool); n = max(0, len(z)-warmup)
    if policy == "full_control":
        return m
    if policy in ("mcar30", "mcar50"):
        m[warmup:] = rng.random(n) < (0.3 if policy == "mcar30" else 0.5)
    elif policy == "block30":
        width = math.ceil(0.3*n)
        if width:
            start = warmup + int(rng.integers(n-width+1))
            m[start:start+width] = True
    elif policy == "mnar_state":
        m[warmup:] = rng.random(n) < np.where(z[warmup:] == 0, 0.15, 0.75)
    else:
        raise ValueError(f"Unknown mask policy: {policy}")
    return m


def mask_observations(segment, policy, study_id, source_id, train_seed, mask_seed, warmup):
    seed = stable_seed(study_id, source_id, segment.entity, segment.partition,
                       train_seed, policy, mask_seed, segment.segment_id, "observation-mask-v1")
    m = generate_mask(segment.states, policy, seed, warmup)
    observed = np.where(m, -1, segment.states).astype(np.int8)
    visible = np.where(m, np.nan, segment.values)
    return observed, visible, m, seed
