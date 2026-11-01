from dataclasses import fields
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
import numpy as np
from ..contracts import EvaluationSegment, Segment, MODELS
from ..features import causal_features
from ..fitting import make_inputs
from ..evaluation import save_inputs, load_inputs, input_fingerprints, corrupt_observed, compare_pool
from ..masking import stable_seed, generate_mask


class FakeBinaryModel:
    classes_ = np.array([0,1])
    def predict_proba(self,x):
        p=.5+.2*np.tanh(x[:,0])
        return np.column_stack([1-p,p])


def fake_bundle(training_seed=11):
    return {'training_mask_seed':training_seed,'median':0.,'scale':1.,'transition':np.array([[.8,.2],[.3,.7]]),
            'prior':np.array([.5,.5]),'state_prevalence':.5,'constant':.15,'development_default':'SOFT_EM_HGB',
            'models':{m:FakeBinaryModel() for m in MODELS if m not in ('CONSTANT','MARKOV')},
            'fit_metadata':{'supervised_fits':0,'HGB_fits':0,'test_double':True}}


class ContractTests(unittest.TestCase):
    def test_public_evaluator_contract_has_no_truth_or_raw_values(self):
        names={f.name for f in fields(EvaluationSegment)}
        self.assertFalse(names & {'truth','states','values','corruption_locations','propensity'})

    def test_features_do_not_read_current_future(self):
        values=np.arange(45,dtype=float);changed=values.copy();changed[30:]=10000
        np.testing.assert_allclose(causal_features(values,24,0,1)[:31],causal_features(changed,24,0,1)[:31])

    def test_whole_forecast_invariant_to_hidden_numeric_values(self):
        cfg={'study_id':'test-only','time_grid_and_target':{'K':3,'warmup_per_segment':24}}
        values=np.sin(np.arange(90));states=(values>0).astype(np.int8)
        segment=Segment('s','entity','selection',np.array([str(i) for i in range(90)]),values,states,np.arange(90)>=24)
        seed=stable_seed('test-only','source','entity','selection',11,'mcar30',11,'s','observation-mask-v1')
        mask=generate_mask(states,'mcar30',seed,24)
        changed=values.copy();changed[mask]=1e9
        alternate=Segment(segment.segment_id,segment.entity,segment.partition,segment.keys,changed,states,segment.score)
        a,_=make_inputs([segment],fake_bundle(),cfg,'source','mcar30',11)
        b,_=make_inputs([alternate],fake_bundle(),cfg,'source','mcar30',11)
        self.assertEqual(input_fingerprints(a),input_fingerprints(b))

    def test_npz_roundtrip_and_corruption_freeze_scores(self):
        inputs=[EvaluationSegment('a',np.array(['a0','a1','a2','a3']),np.array([1,-1,1,0]),np.array([0,0,0,1],bool),np.full((6,4),.2))]
        with TemporaryDirectory() as td:
            path=Path(td)/'p.npz';save_inputs(path,inputs);restored=load_inputs(path)
            self.assertEqual(input_fingerprints(inputs),input_fingerprints(restored))
        changed,positions=corrupt_observed(inputs,2,42)
        self.assertEqual(len(positions),2)
        self.assertEqual(input_fingerprints(inputs),input_fingerprints(changed))
        self.assertEqual(int(np.sum(inputs[0].observed!=changed[0].observed)),2)

    def test_empty_known_subset_is_NA_not_zero_loss(self):
        inputs=[EvaluationSegment('a',np.array([str(i) for i in range(8)]),np.full(8,-1),np.arange(8)>=3,np.full((6,8),.2))]
        _,points,_=compare_pool(inputs,np.array([[.8,.2],[.3,.7]]),np.array([.5,.5]),.4)
        for row in points:
            if row['estimator'] in ('complete_case','logically_known'):
                self.assertIsNone(row['estimated_risk']);self.assertEqual(row['n_used'],0)

    def test_identical_forecasts_are_not_mislabeled_as_missing_information(self):
        inputs=[EvaluationSegment('a',np.array([str(i) for i in range(8)]),np.full(8,-1),np.arange(8)>=3,np.full((6,8),.2))]
        pairs,_,_=compare_pool(inputs,np.array([[.8,.2],[.3,.7]]),np.array([.5,.5]),.4)
        self.assertTrue(all(r['verdict']=='INCONCLUSIVE' for r in pairs))
        self.assertTrue(all(r['reason']=='no_strict_difference_within_tolerance' for r in pairs))
