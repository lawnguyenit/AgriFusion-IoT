"""Explicit calendar folds; train-only threshold, immutable gaps and segment resets."""
import numpy as np
import pandas as pd
from ..reference_evaluation.contracts import HOUR_NS
from ..reference_evaluation.targets import end_labels
from ..reference_evaluation.preparation import segments_from_frame


def prepare(hourly,fold,config):
    d=hourly.copy();end=pd.Timestamp(fold['assessment_end']).value
    d=d[d.timestamp<end].sort_values('timestamp',kind='stable').reset_index(drop=True)
    if d.timestamp.duplicated().any() or d.sample_id.duplicated().any():raise ValueError('Duplicate hourly keys')
    cuts=np.array([pd.Timestamp(fold[n]).value for n in ('train_end','development_end','selection_end')])
    if not np.all(np.diff(cuts)>0):raise ValueError('Fold boundaries not ordered')
    d['partition']=np.array(['train','development','selection','assessment'])[np.searchsorted(cuts,d.timestamp,side='right')]
    train=d.loc[d.partition=='train','value'].to_numpy(float);train=train[np.isfinite(train)]
    if not len(train):raise ValueError('No finite training reference')
    threshold=float(np.quantile(train,config['quantile']))
    d['threshold']=threshold;d['F']=np.where(np.isfinite(d.value),(d.value>threshold).astype(int),-1).astype(np.int8)
    d['segment_id']='';d['score']=False;d['END_audit']=-1
    finite=d.F>=0
    breaks=(d.partition!=d.partition.shift())|(~finite)|(~finite.shift(fill_value=False))|(d.timestamp.diff()!=HOUR_NS)
    group=breaks.cumsum();k=config['K'];warmup=config['warmup']
    for _,rows in d[finite].groupby(group[finite],sort=False):
        ix=rows.index;sid=f"{fold['id']}__{rows.partition.iloc[0]}__{int(ix[0]):06d}"
        d.loc[ix,'segment_id']=sid;d.loc[ix,'score']=np.arange(len(ix))>=warmup
        d.loc[ix,'END_audit']=end_labels(rows.F.to_numpy(np.int8),k)
    segments=segments_from_frame(d);support=[]
    for part in ('train','development','selection','assessment'):
        rows=d[d.partition==part];scored=rows[rows.score];positive=int((scored.END_audit==1).sum());negative=int((scored.END_audit==0).sum())
        support.append({'fold':fold['id'],'partition':part,'rows':len(rows),'finite_rows':int((rows.F>=0).sum()),
                        'scored':len(scored),'END_positive':positive,'END_negative':negative,'threshold_train_q75':threshold,
                        'status':'adequate_for_declared_support_gate' if positive>=config['support_min_positive'] and negative>=config['support_min_negative'] else 'limited_support',
                        'minimum_timestamp':int(rows.timestamp.min()) if len(rows) else None,'maximum_timestamp':int(rows.timestamp.max()) if len(rows) else None})
    owners={}
    for s in segments:
        for key in s.keys:
            if key in owners:raise ValueError('Origin reused across segments/partitions')
            owners[key]=s.partition
    return d,segments,support
