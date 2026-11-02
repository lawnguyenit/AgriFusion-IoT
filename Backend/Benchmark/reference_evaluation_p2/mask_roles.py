"""Role-separated masks; simulated source adapter never enters evaluator."""
import numpy as np
from ..reference_evaluation.masking import stable_seed, generate_mask
from ..reference_evaluation.contracts import EvaluationSegment
from ..reference_evaluation.fitting import predict_segment


def role_mask(segment, policy, seed, source, role, warmup=24):
    if role not in ('feature', 'reference') or policy not in ('mcar30', 'block30'):
        raise ValueError('P2 only supports declared independent MCAR30/block30 roles')
    derived = stable_seed('reference_evaluation_p2_v1', source, segment.entity,
                          segment.partition, 11, policy, int(seed), segment.segment_id, role)
    return generate_mask(segment.states, policy, derived, warmup), derived


def forecast(reference, bundle, policy, seed, source, k, warmup):
    inputs = []; seeds = []
    for s in reference:
        hidden, derived = role_mask(s, policy, seed, source, 'feature', warmup)
        observed = np.where(hidden, -1, s.states).astype(np.int8)
        visible = np.where(hidden, np.nan, s.values)
        inputs.append(predict_segment(s.segment_id, s.keys, s.score, bundle, observed, visible, k))
        seeds.append({'segment_id':s.segment_id, 'role':'feature', 'seed':int(seed), 'effective_seed':derived})
    return inputs, seeds


def attach_reference(fixed_forecasts, reference, policy, seed, source, warmup, full=False):
    if len(fixed_forecasts) != len(reference):
        raise ValueError('Mask/reference count mismatch')
    result = []; seeds = []
    for p, r in zip(fixed_forecasts, reference):
        if p.segment_id != r.segment_id or not np.array_equal(p.keys, r.keys) or not np.array_equal(p.score, r.score):
            raise ValueError('Mask/reference cohort mismatch')
        hidden, derived = (np.zeros(len(r.states),bool),None) if full else role_mask(r,policy,seed,source,'reference',warmup)
        observed = np.where(hidden,-1,r.states).astype(np.int8)
        # Numeric values/full truth are never fields of the evaluator object.
        s = EvaluationSegment(p.segment_id,p.keys.copy(),observed,p.score.copy(),p.probabilities.copy())
        s.validate(); result.append(s)
        seeds.append({'segment_id':p.segment_id,'role':'reference','seed':int(seed),'effective_seed':derived,'full_reference':full})
    return result,seeds
