from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from ...reference_evaluation.contracts import Segment, EvaluationSegment
from ...reference_evaluation.bounds import segment_frontier
from ...reference_evaluation.evaluation import input_fingerprints
from ..witness import trace_segment,trace_pool,primary_bounds
from ..validation import labels,score_witness,recheck_saved,classify
from ..mask_roles import role_mask,attach_reference
from ..persistence import save_witness


class PilotTests(unittest.TestCase):
    def test_trace_against_exhaustive_oracle_and_rolling_frontier(self):
        rng=np.random.default_rng(731)
        for k in (1,2,3):
            for _ in range(12):
                o=rng.integers(-1,2,7); w=rng.normal(size=7)
                possible=[]
                for bits in product((0,1),repeat=7):
                    if all(obs<0 or obs==bit for obs,bit in zip(o,bits)):
                        # Direct scalar conjunction independent of both DP paths.
                        ys=[int(t>=k and bits[t]==0 and all(bits[t-j]==1 for j in range(1,k+1))) for t in range(7)]
                        possible.append(float(np.dot(w,ys)))
                oldlo,oldhi=segment_frontier(o,w,k,0)
                for direction,expected,old in [('min',min(possible),oldlo[0]),('max',max(possible),oldhi[0])]:
                    z,value=trace_segment(o,w,k,direction)
                    self.assertAlmostEqual(value,expected,places=11)
                    self.assertAlmostEqual(value,old,places=11)
                    self.assertAlmostEqual(float(w@labels(z,k)),expected,places=11)
                    self.assertTrue(np.array_equal(z[o>=0],o[o>=0]))

    def test_role_namespaces_invariance_and_full_control(self):
        n=100;states=(np.arange(n)%5==0).astype(np.int8);score=np.arange(n)>=24
        ref=Segment('s','e','selection',np.array([f'k{i}' for i in range(n)]),np.arange(n,dtype=float),states,score)
        p=np.tile(np.linspace(0,1,n),(6,1)); original=EvaluationSegment('s',ref.keys,states.copy(),score,p)
        for policy in ('mcar30','block30'):
            _,fseed=role_mask(ref,policy,11,'source','feature')
            _,rseed=role_mask(ref,policy,11,'source','reference')
            self.assertNotEqual(fseed,rseed)
            for seed in (11,22):
                changed,_=attach_reference([original],[ref],policy,seed,'source',24)
                self.assertEqual(input_fingerprints(changed),input_fingerprints([original]))
                self.assertFalse(hasattr(changed[0],'states'))
                self.assertFalse(hasattr(changed[0],'values'))
            full,_=attach_reference([original],[ref],policy,0,'source',24,full=True)
            low,high=primary_bounds(full)
            self.assertAlmostEqual(low,high,places=12)

    def test_segment_boundaries_and_saved_witness_tampering(self):
        inputs=[]
        for sid in ('left','right'):
            inputs.append(EvaluationSegment(sid,np.array([sid+str(i) for i in range(7)]),
                np.array([1,1,-1,0,-1,-1,0],dtype=np.int8),np.arange(7)>=3,
                np.array([[0.2]*7,[0.8]*7,[0.3]*7,[0.1]*7,[0.6]*7,[0.4]*7])))
        low,high=primary_bounds(inputs)
        for direction,endpoint in [('min',low),('max',high)]:
            z=trace_pool(inputs,direction=direction)
            result,y=score_witness(inputs,z,3,3,endpoint)
            self.assertEqual(result['observed_errors_global'],0)
            for yy in y:self.assertTrue(np.array_equal(yy[:3],np.zeros(3)))
            with TemporaryDirectory() as temp:
                path=Path(temp)/'w.npz';save_witness(path,inputs,z,y)
                self.assertTrue(recheck_saved(path,inputs,3,3,endpoint))
                with np.load(path,allow_pickle=False) as data:corrupt={k:data[k] for k in data.files}
                corrupt['END']=1-corrupt['END'];np.savez(path,**corrupt)
                with self.assertRaisesRegex(ValueError,'END'):recheck_saved(path,inputs,3,3,endpoint)
        bad=trace_pool(inputs);bad[0][0]=0
        with self.assertRaisesRegex(ValueError,'R0'):score_witness(inputs,bad,3,3)

    def test_invalid_contracts_and_classifications(self):
        for obs,w in [([2],[0]),([-1],[float('nan')]),([0],[0,1])]:
            with self.assertRaises(ValueError):trace_segment(obs,w)
        with self.assertRaises(ValueError):trace_pool([],budget=1)
        self.assertEqual(classify(-0.1,0.1),'opposite_strict_orders_attained_float_verified')
        self.assertEqual(classify(0,0),'tie_within_tolerance')
        self.assertEqual(classify(0,0.1),'endpoint_touches_zero_within_tolerance')
        self.assertEqual(classify(-0.1,0.1,endpoint_error=1e-5),'numerically_unresolved')


if __name__=='__main__':unittest.main()
