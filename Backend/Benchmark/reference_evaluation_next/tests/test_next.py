from itertools import product
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from ...reference_evaluation.contracts import EvaluationSegment,MODELS,Segment,HOUR_NS
from ...reference_evaluation_p2.validation import labels
from ..analysis import compare,ht,state_influence
from ..mechanisms import trace,schedules,masked
from ..source235 import aggregate
from ..folds import prepare
from ..mask_adapter import reference_inputs,role_mask
from ..journal import Journal,verify


class NextTests(unittest.TestCase):
    def test_synthetic_probabilities_strictly_causal(self):
        z=trace(256,.8,11)
        for k in (1,3,6):
            for alpha in (.25,1):
                p=schedules(z,k,.8,alpha);changed=z.copy();changed[33:]=1-changed[33:]
                self.assertTrue(np.array_equal(p[:,:34],schedules(changed,k,.8,alpha)[:,:34]))
                self.assertTrue(np.isfinite(p).all() and (p>=0).all() and (p<=1).all())

    def test_matched_placement_and_influence_bound(self):
        z=trace(256,.8,22);p=schedules(z,3,.8,1)
        high,h=masked(z,p,3,22,'high_I_block');low,l=masked(z,p,3,22,'low_I_block')
        self.assertEqual(h['hidden_count'],l['hidden_count']);self.assertEqual(h['block_length'],l['block_length'])
        self.assertGreaterEqual(h['hidden_I_sum'],l['hidden_I_sum']-1e-12)
        self.assertTrue(np.array_equal(high.probabilities,low.probabilities))
        I=state_influence(p,high.score,3);y=labels(z,3)
        for s in range(len(z)):
            changed=z.copy();changed[s]=1-changed[s]
            effect=abs(float(((-2*(p[1]-p[0]))*(labels(changed,3)-y)*high.score).sum()/high.score.sum()))
            self.assertLessEqual(effect,I[s]+1e-12)

    def test_all_pairs_G_against_exhaustive_completions(self):
        z=np.array([1,1,0,1,0,0],dtype=np.int8);obs=np.array([1,-1,-1,1,-1,0],dtype=np.int8)
        p=np.random.default_rng(55).random((6,6));score=np.arange(6)>=2
        public=EvaluationSegment('toy',np.array(list('abcdef')),obs,score,p)
        _,_,candidates,decisions,_,_=compare([public],[z],np.array([[.8,.2],[.2,.8]]),np.array([.5,.5]),.5,1)
        losses=[]
        for bits in product((0,1),repeat=6):
            if all(o<0 or b==o for b,o in zip(bits,obs)):
                losses.append(np.mean((p[:,score]-labels(np.array(bits),1)[score])**2,axis=1))
        for i,m in enumerate(MODELS):
            expected=max(row[i]-min(row) for row in losses)
            actual=next(r['G'] for r in candidates if r['approach']=='joint' and r['model']==m)
            self.assertAlmostEqual(actual,expected,places=11)

    def test_HT_enumerated_expectation_and_warmup_pi(self):
        z=np.array([1,1,1,0,1,1,0,0],dtype=np.int8);p=np.random.default_rng(11).random((6,8));score=np.arange(8)>=3
        expected=np.mean((p[:,score]-labels(z,3)[score])**2,axis=1);total=np.zeros(6);q=.7
        for bits in product((0,1),repeat=5):
            observed=z.copy();keep=np.array(bits,dtype=bool);observed[3:]=np.where(keep,z[3:],-1)
            s=EvaluationSegment('s',np.array([str(i) for i in range(8)]),observed,score,p)
            values=ht([s],3,q,3);prob=q**sum(bits)*(1-q)**(5-sum(bits))
            total+=prob*np.array([r['estimated_risk'] for r in values])
        np.testing.assert_allclose(total,expected,rtol=0,atol=1e-12)

    def test_hourly_partial_duplicate_and_invalid_unknown(self):
        times=pd.date_range('2007-01-01',periods=180,freq='min');values=np.ones(180)
        d=pd.DataFrame({'timestamp':times,'value':values});d.loc[61,'value']=np.nan
        extra=d.iloc[[120]].copy();d=pd.concat([d,extra],ignore_index=True)
        a=aggregate(d);self.assertEqual(a.value.iloc[0],1);self.assertTrue(np.isnan(a.value.iloc[1]));self.assertTrue(np.isnan(a.value.iloc[2]))
        self.assertTrue(np.isnan(aggregate(d.iloc[:59]).value.iloc[0]))

    def test_temporal_threshold_and_boundary_resets(self):
        n=240;t=pd.date_range('2007-01-01',periods=n,freq='h').astype('int64')
        d=pd.DataFrame({'timestamp':t,'sample_id':[str(i) for i in range(n)],'entity':'e','value':np.arange(n)%9})
        fold={'id':'toy','train_end':'2007-01-04','development_end':'2007-01-06','selection_end':'2007-01-08','assessment_end':'2007-01-11'}
        c={'K':3,'warmup':24,'quantile':.75,'support_min_positive':1,'support_min_negative':1}
        a,segments,_=prepare(d,fold,c);changed=d.copy();changed.loc[changed.timestamp>=pd.Timestamp('2007-01-08').value,'value']=100
        b,_,_=prepare(changed,fold,c);self.assertEqual(a.threshold.iloc[0],b.threshold.iloc[0])
        for s in segments:self.assertFalse(s.score[:24].any());self.assertTrue(np.array_equal(labels(s.states,3)[:3],np.zeros(3)))

    def test_independent_role_and_fixed_prediction(self):
        n=60;z=np.arange(n)%2;s=Segment('s','e','selection',np.array([str(i) for i in range(n)]),np.arange(n,dtype=float),z,np.arange(n)>=24)
        public=EvaluationSegment('s',s.keys,z,s.score,np.full((6,n),.25))
        _,a=role_mask(s,'mcar30',11,'F1',22,'feature');_,b=role_mask(s,'mcar30',11,'F1',22,'reference');self.assertNotEqual(a,b)
        for seed in (11,22,33):
            changed,_=reference_inputs([public],[s],'mcar30',seed,'F1',22)
            np.testing.assert_array_equal(changed[0].probabilities,public.probabilities)

    def test_journal_tamper_and_reuse(self):
        with TemporaryDirectory() as tmp:
            j=Journal(tmp)
            with j.unit('test','one',['data.txt']) as (p,reused):
                self.assertFalse(reused);(p/'data.txt').write_text('immutable')
            verify(p)
            with j.unit('test','one',['data.txt']) as (q,reused):self.assertTrue(reused)
            (p/'data.txt').write_text('changed')
            with self.assertRaises(ValueError):verify(p)

    def test_primary_metadata_uses_declared_orientation(self):
        from ..p3 import case
        from ..journal import read
        from ...reference_evaluation.contracts import verdict
        import csv
        with TemporaryDirectory() as tmp:
            unit,row=case(Journal(tmp),.8,3,1.,11,'fixed_count_random',48,'test_case')
            with (unit/'primary_sensitivity.csv').open(encoding='utf-8',newline='') as f:
                r=next(r for r in csv.DictReader(f) if r['R_global']=='0')
            self.assertEqual(row['primary_model_a'],r['model_a'])
            self.assertEqual(row['primary_model_b'],r['model_b'])
            self.assertEqual(row['primary_verdict'],verdict(float(r['joint_lower']),float(r['joint_upper'])))


if __name__=='__main__':unittest.main()
