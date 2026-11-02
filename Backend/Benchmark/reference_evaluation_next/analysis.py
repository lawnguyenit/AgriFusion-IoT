"""All-pairs comparisons reuse the v1 numerical owner; generic pool reporting."""
from itertools import combinations
import csv
import numpy as np
from ..reference_evaluation.contracts import MODELS
from ..reference_evaluation.evaluation import compare_pool,input_fingerprints
from ..reference_evaluation.decisions import oriented_interval
from ..reference_evaluation.targets import marginal_labels


def table(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        names=list(dict.fromkeys(k for r in rows for k in r))
        w=csv.DictWriter(f,fieldnames=names);w.writeheader();w.writerows(rows)


def compare(inputs,reference_states,transition,prior,prevalence,k,names=MODELS):
    pairs,points,info=compare_pool(inputs,transition,prior,prevalence,k)
    candidates,decisions=pool_decisions(pairs,names)
    n=sum(int(s.score.sum()) for s in inputs)
    truth=np.zeros(6)
    from ..reference_evaluation_p2.validation import labels
    if len(inputs)!=len(reference_states):raise ValueError('Audit segment count')
    for s,z in zip(inputs,reference_states):
        y=labels(z,k);truth+=((s.probabilities[:,s.score]-y[s.score])**2).sum(axis=1)
    truth/=n
    for r in pairs:
        a,b=MODELS.index(r['model_a']),MODELS.index(r['model_b']);delta=float(truth[a]-truth[b])
        for kind in ('joint','rectangle','separate'):
            if not r[kind+'_lower']-1e-9<=delta<=r[kind+'_upper']+1e-9:raise AssertionError('Truth outside '+kind)
        r['true_delta_audit']=delta
    for r in candidates:
        m=names.index(r['model']);r.update(audit_brier=float(truth[m]),audit_regret=float(truth[m]-truth.min()))
        if r['audit_regret']>r['G']+1e-9:raise AssertionError('Audit regret exceeds guaranteed bound')
    for r in decisions:r['audit_regret']=float(truth[names.index(r['selected_model'])]-truth.min())
    rename=dict(zip(MODELS,names))
    for r in pairs:r['model_a']=rename[r['model_a']];r['model_b']=rename[r['model_b']]
    for r in points:r['model']=rename[r['model']]
    risks=[{'model':name,'true_brier_audit':float(truth[i]),'n_scored':n} for i,name in enumerate(names)]
    return pairs,points,candidates,decisions,risks,info


def pool_decisions(pairs,names=MODELS):
    """Choices consume bounds only; full/audit truth is not an argument."""
    candidates=[];decisions=[]
    for kind in ('joint','rectangle','separate'):
        rows=[{**r,'joint_lower':r[kind+'_lower'],'joint_upper':r[kind+'_upper']} for r in pairs]
        for m,name in enumerate(names):
            G=max([0.0]+[oriented_interval(rows,MODELS[m],other)[1] for other in MODELS if other!=MODELS[m]])
            candidates.append({'approach':kind,'model':name,'G':float(G),'bound_role':'exact_on_declared_temporal_set' if kind=='joint' else 'conservative_upper_bound'})
        group=[r for r in candidates if r['approach']==kind];g=min(r['G'] for r in group)
        selected=sorted(r['model'] for r in group if r['G']<=g+1e-12)[0]
        chosen=next(r for r in group if r['model']==selected)
        decisions.append({'approach':kind,'selected_model':selected,'G_star':g,'selected_G':chosen['G']})
    return candidates,decisions


def ht(inputs,k,q=0.7,warmup=24):
    """Reference-only Bernoulli MCAR; do not call for block/shared/MNAR."""
    sums=np.zeros(6);n=0;used=0
    for s in inputs:
        _,_,known,complete=marginal_labels(s.observed,k)
        t=np.arange(len(s.keys));mutable=np.minimum(k+1,np.maximum(0,t-warmup+1))
        pi=q**mutable;use=complete&s.score
        sums+=(((s.probabilities[:,use]-known[use])**2)/pi[use]).sum(axis=1)
        n+=int(s.score.sum());used+=int(use.sum())
    return [{'estimator':'HT_independent_reference_MCAR','model':m,'estimated_risk':float(sums[i]/n),'n_used':used,'n_scored':n,'clipped':False} for i,m in enumerate(MODELS)]


def state_influence(probabilities,score,k,a=1,b=0):
    w=np.abs(-2*(probabilities[a]-probabilities[b])*score/max(1,int(score.sum())))
    return np.array([float(w[s:min(len(w),s+k+1)].sum()) for s in range(len(w))])
