from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
import numpy as np
import pandas as pd
from ..storage import RunStore, verify_ready
from ..stages import audit_source, load_prepared, fit_source, evaluate_case
from ..sensitivity import sensitivity_case
from ..solver_stage import solve_case
from ..reporting import write_report, export_sync_tree
from .test_contracts import fake_bundle


class PipelineIntegrationTests(unittest.TestCase):
    def test_real_adapters_to_results_and_resume_with_stub_forecasters(self):
        """Synthetic CSV; actual learners are replaced, so NO HGB fit occurs."""
        with TemporaryDirectory() as td:
            root=Path(td);archive=root/'synthetic_energy.csv'
            hours=480;times=pd.date_range('2020-01-01',periods=hours*6,freq='10min')
            pd.DataFrame({'date':times,'RH_1':np.repeat(np.arange(hours)%20,6)}).to_csv(archive,index=False)
            cfg=json.loads((Path(__file__).parents[1]/'configs/recorded_hourly_v1.json').read_text())
            cfg['study_id']='synthetic_contract_test_not_science'
            cfg['sources']=[cfg['sources'][1]];cfg['training']['training_mask_seeds']=[11]
            cfg['evaluation_masks']['policies']=['full_control','mcar30'];cfg['evaluation_masks']['mask_seeds']=[11]
            cfg['runtime']['local_archives']={'appliances_energy_374':str(archive)}
            store=RunStore(root/'out',cfg,argv=['synthetic-test-no-real-fit'])
            source=cfg['sources'][0]
            audit_dir=audit_source(store,source)
            segments,metadata=load_prepared(audit_dir)
            self.assertTrue(metadata['hard_gate_passed'])
            with patch('Backend.Benchmark.reference_evaluation.fitting.fit_candidates',return_value=fake_bundle()):
                fit_dir=fit_source(store,source['dataset_id'],11,audit_dir,segments,metadata)
            cases=[]
            for policy,seed in [('full_control',0),('mcar30',11)]:
                case=evaluate_case(store,source['dataset_id'],11,policy,seed,audit_dir,fit_dir,segments,metadata)
                verify_ready(case);cases.append(case)
                sensitivity_case(store,case)
            solves=solve_case(store,cases[1]);self.assertEqual(len(solves),4)
            report=write_report(store)
            risks=pd.read_csv(report/'model_risks.csv')
            self.assertEqual(set(risks.model),{'COMPLETE_HGB','SOFT_EM_HGB','MARKOV','CONSTANT','LOGISTIC_COMPLETE_H6','HGB_COMPLETE_H24'})
            self.assertEqual(len(pd.read_csv(report/'pair_bounds.csv')),60)
            self.assertFalse(json.loads((report/'metrics.json').read_text())['full_plan_complete'])
            (cases[0]/'unlisted_extra.txt').write_text('must not be silently exported')
            export=export_sync_tree(store)
            exported=json.loads((export/'EXPORT_MANIFEST.json').read_text())
            self.assertFalse(exported['uploaded_to_drive']);self.assertTrue(exported['files'])
            self.assertFalse(any(r['path'].endswith('unlisted_extra.txt') for r in exported['files']))
            self.assertTrue((export/'ACTIVE_GRAPH.json').exists())
            # Resume must reuse forecasts without invoking a learner.
            store.resume=True
            with patch('Backend.Benchmark.reference_evaluation.fitting.fit_candidates',side_effect=AssertionError('unexpected refit')):
                again=fit_source(store,source['dataset_id'],11,audit_dir,segments,metadata)
            self.assertEqual(fit_dir,again)
            self.assertEqual(len(store.active_units('evaluate')),2)
            store.finish_invocation(0)
