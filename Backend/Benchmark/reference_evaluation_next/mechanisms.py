"""Locked synthetic processes, causal probability schedules and mask placement."""
import math
import numpy as np
from ..reference_evaluation.masking import stable_seed
from ..reference_evaluation.contracts import EvaluationSegment
from .analysis import state_influence


def trace(length,persistence,seed):
    rng=np.random.default_rng(stable_seed('P3_trace',persistence,seed));z=np.empty(length,dtype=np.int8)
    z[0]=rng.integers(0,2)
    for t in range(1,length):z[t]=z[t-1] if rng.random()<persistence else 1-z[t-1]
    return z


def schedules(z,k,persistence,alpha):
    base=.5*persistence**(k-1)*(1-persistence)
    p=np.full((6,len(z)),base)
    for t in range(k,len(z)):
        history=z[t-k:t];run=float(np.all(history==1));recent=z[max(0,t-6):t]
        p[1,t]=run*(1-persistence)
        p[2,t]=run*.5
        p[3,t]=float(np.mean(recent))**k*(1-persistence)
        p[4,t]=float(np.mean(history))**k*(1-persistence)
        p[5,t]=float(t>k and np.all(z[t-k-1:t-1]==1))*(1-persistence)
    return base+alpha*(p-base)


def masked(z,p,k,seed,policy,warmup=24,fraction=.3):
    score=np.arange(len(z))>=warmup;influence=state_influence(p,score,k)
    width=math.ceil(fraction*int(score.sum()));mask=np.zeros(len(z),dtype=bool)
    rng=np.random.default_rng(stable_seed('P3_mask',seed,policy))
    start=None
    if policy=='fixed_count_random':mask[rng.choice(np.flatnonzero(score),size=width,replace=False)]=True
    else:
        starts=np.arange(warmup,len(z)-width+1)
        totals=np.array([influence[s:s+width].sum() for s in starts])
        if policy=='random_block':start=int(rng.choice(starts))
        elif policy=='high_I_block':start=int(starts[np.argmax(totals)])
        elif policy=='low_I_block':start=int(starts[np.argmin(totals)])
        else:raise ValueError('Unknown placement')
        mask[start:start+width]=True
    keys=np.array([f'origin_{t:04d}' for t in range(len(z))])
    public=EvaluationSegment('synthetic_segment',keys,np.where(mask,-1,z).astype(np.int8),score,p.copy())
    public.validate()
    metadata={'hidden_count':int(mask.sum()),'missing_fraction':float(mask[score].mean()),'block_start':start,
              'block_length':width if start is not None else None,'hidden_I_sum':float(influence[mask].sum()),
              'I_sum_all_states':float(influence.sum())}
    return public,metadata
