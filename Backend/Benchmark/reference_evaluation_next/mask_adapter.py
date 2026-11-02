"""Train/fold-aware independent feature/reference roles for P4."""
import numpy as np
from ..reference_evaluation.masking import generate_mask,stable_seed
from ..reference_evaluation.fitting import predict_segment
from ..reference_evaluation.contracts import EvaluationSegment


def role_mask(segment,policy,seed,fold,training_seed,role,warmup=24):
    derived=stable_seed('P4_independent_roles',fold,training_seed,segment.partition,segment.segment_id,policy,seed,role)
    mask=generate_mask(segment.states,policy,derived,warmup)
    return mask,derived


def forecasts(segments,bundle,regime,seed,fold,k=3,warmup=24):
    inputs=[];records=[];policy='full_control' if regime=='full' else 'mcar30'
    for s in segments:
        mask,derived=role_mask(s,policy,seed,fold,bundle['training_mask_seed'],'feature',warmup)
        observed=np.where(mask,-1,s.states).astype(np.int8);visible=np.where(mask,np.nan,s.values)
        inputs.append(predict_segment(s.segment_id,s.keys,s.score,bundle,observed,visible,k))
        records.append({'segment_id':s.segment_id,'role':'feature','policy':policy,'seed':seed,'effective_seed':derived})
    return inputs,records


def reference_inputs(fixed,segments,policy,seed,fold,training_seed,warmup=24):
    result=[];records=[]
    if len(fixed)!=len(segments):raise ValueError('Reference size mismatch')
    for p,s in zip(fixed,segments):
        if p.segment_id!=s.segment_id or not np.array_equal(p.keys,s.keys) or not np.array_equal(p.score,s.score):raise ValueError('Reference cohort mismatch')
        mask,derived=role_mask(s,policy,seed,fold,training_seed,'reference',warmup)
        public=EvaluationSegment(p.segment_id,p.keys.copy(),np.where(mask,-1,s.states).astype(np.int8),p.score.copy(),p.probabilities.copy())
        public.validate();result.append(public)
        records.append({'segment_id':s.segment_id,'role':'reference','policy':policy,'seed':seed,'effective_seed':derived})
    return result,records
