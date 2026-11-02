"""Controlled mechanism pilot and explicit held-out gate; no forecaster fits."""
from itertools import product
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
import argparse,json
import numpy as np
from ..reference_evaluation.evaluation import save_inputs,primary_sensitivity
from ..reference_evaluation_p2.witness import trace_pool
from ..reference_evaluation_p2.validation import score_witness,labels,recheck_saved
from ..reference_evaluation_p2.persistence import save_witness
from .journal import Journal,write,read,verify
from .analysis import compare,table
from .mechanisms import trace,schedules,masked


def case(journal,persistence,k,alpha,seed,policy,length,stage):
    c=journal.protocol['mechanisms'];key=f'p{persistence}_K{k}_a{alpha}_s{seed}_{policy}'
    with journal.unit(stage,key,['case.json','pair_bounds.csv','candidate_guarantees.csv','public_inputs.npz','witness_validation.json']) as (out,reused):
        if not reused:
            z=trace(length,persistence,seed);p=schedules(z,k,persistence,alpha)
            public,metadata=masked(z,p,k,seed,policy,c['warmup'],c['hidden_fraction'])
            transition=np.array([[persistence,1-persistence],[1-persistence,persistence]])
            pairs,points,candidates,decisions,risks,info=compare([public],[z],transition,np.array([.5,.5]),.5,k,c['synthetic_names'])
            table(out/'pair_bounds.csv',pairs);table(out/'candidate_guarantees.csv',candidates)
            table(out/'point_estimates.csv',points);table(out/'decisions.csv',decisions);table(out/'model_risks.csv',risks)
            save_inputs(out/'public_inputs.npz',[public]);audit=out/'audit_only';audit.mkdir()
            np.savez_compressed(audit/'truth.npz',F=z,END=labels(z,k),keys=public.keys)
            primary=next(r for r in pairs if r['model_a']==c['synthetic_names'][0] and r['model_b']==c['synthetic_names'][1])
            low,high=-primary['joint_upper'],-primary['joint_lower'];checks=[]
            for direction,value in [('min',low),('max',high)]:
                completion=trace_pool([public],k,direction);result,y=score_witness([public],completion,k,c['warmup'],value)
                file=out/(direction+'_witness.npz');save_witness(file,[public],completion,y)
                recheck_saved(file,[public],k,c['warmup'],value);checks.append({'direction':direction,**result})
            write(out/'witness_validation.json',checks)
            sensitivity=primary_sensitivity([public],c['diagnostic_R'],k)
            for r in sensitivity:
                r['model_a']=c['synthetic_names'][1];r['model_b']=c['synthetic_names'][0]
                r['scope']='primary pair only; no all-pool G at R>0'
            table(out/'primary_sensitivity.csv',sensitivity)
            row={'persistence':persistence,'K':k,'alpha':alpha,'seed':seed,'mask':policy,
                 'trace_length':length,'END_density_audit':float(labels(z,k)[public.score].mean()),
                 **metadata,'prediction_sha256':info['prediction_sha256'],'cohort_sha256':info['cohort_sha256'],
                 'joint_width':primary['joint_upper']-primary['joint_lower'],
                 'rectangle_width':primary['rectangle_upper']-primary['rectangle_lower'],
                 'separate_width':primary['separate_upper']-primary['separate_lower'],
                 'joint_G_star':next(r['G_star'] for r in decisions if r['approach']=='joint'),
                 'primary_verdict':primary['verdict'],'source_run_id':out.name,
                 'synthetic_not_trained_forecasters':True}
            write(out/'case.json',row)
            write(out/'synthetic_aliases.json',{'internal_positions_only':dict(zip(['COMPLETE_HGB','SOFT_EM_HGB','MARKOV','CONSTANT','LOGISTIC_COMPLETE_H6','HGB_COMPLETE_H24'],c['synthetic_names'])),'note':'No learner trained; internal names are six-slot serialization aliases only'})
    return out,read(out/'case.json')


def run(root):
    j=Journal(root);c=j.protocol['mechanisms'];smoke=[]
    # Twelve fixed smoke cases before main; count independent of outcomes.
    for k,persistence,policy in product(c['K'],[c['persistence'][0],c['persistence'][-1]],['fixed_count_random','random_block']):
        out,row=case(j,persistence,k,1.,11,policy,48,'p3_smoke');smoke.append(out)
    rows=[];parents=[]
    for persistence,k,alpha,seed,policy in product(c['persistence'],c['K'],c['alpha'],c['seeds'],c['masks']):
        out,row=case(j,persistence,k,alpha,seed,policy,c['length'],'p3_cases');rows.append(row);parents.append(out/'READY.json')
        if len(rows)%24==0:print(f'P3 {len(rows)}/360',flush=True)
    with j.unit('p3_report','mechanism_summary',['mechanism_cases.csv','contrasts.csv','GATE.json'],parents) as (out,reused):
        if not reused:
            table(out/'mechanism_cases.csv',rows);contrasts=[]
            for persistence,k,alpha,seed in product(c['persistence'],c['K'],c['alpha'],c['seeds']):
                pair={r['mask']:r for r in rows if r['persistence']==persistence and r['K']==k and r['alpha']==alpha and r['seed']==seed}
                high,low=pair['high_I_block'],pair['low_I_block']
                if high['hidden_count']!=low['hidden_count'] or high['prediction_sha256']!=low['prediction_sha256']:raise AssertionError('Unmatched placement contrast')
                group='discovery' if persistence in c['discovery_persistence'] and seed in c['discovery_seeds'] else ('heldout' if persistence in c['heldout_persistence'] and seed in c['heldout_seeds'] else 'descriptive_other')
                contrasts.append({'persistence':persistence,'K':k,'alpha':alpha,'seed':seed,'group':group,
                                  'joint_width_high_minus_low':high['joint_width']-low['joint_width'],
                                  'rectangle_width_high_minus_low':high['rectangle_width']-low['rectangle_width'],
                                  'I_high_minus_low':high['hidden_I_sum']-low['hidden_I_sum'],
                                  'same_missing_fraction':high['missing_fraction']==low['missing_fraction'],
                                  'counterexample':high['joint_width']<low['joint_width']-c['tolerance']})
            table(out/'contrasts.csv',contrasts)
            groups={}
            for name in ['discovery','heldout','descriptive_other']:
                rr=[r for r in contrasts if r['group']==name];effect=[r['joint_width_high_minus_low'] for r in rr]
                groups[name]={'contrasts':len(rr),'median_effect':float(np.median(effect)),'mean_effect':float(np.mean(effect)),
                              'min_effect':float(min(effect)),'max_effect':float(max(effect)),
                              'counterexamples':sum(r['counterexample'] for r in rr),'ties':sum(abs(v)<=c['tolerance'] for v in effect)}
            gate=groups['discovery']['median_effect']>c['tolerance'] and groups['heldout']['median_effect']>c['tolerance']
            write(out/'GATE.json',{'status':'supported_conditional_mechanism' if gate else 'not_supported_do_not_open_P4',
                   'open_P4':gate,'hypothesis':c['hypothesis'],'groups':groups,'smoke_cases':len(smoke),'main_cases':len(rows),
                   'forecaster_fits':0,'p_values':None,'scope':'conditional paired placement effect, no causal isolation of K versus event density',
                   'failure_domain':'I_s is only an upper bound; report zero and reversed contrasts; persistence/K/event density co-vary'})
            all_candidates=[];all_pairs=[];all_sensitivity=[];coverage=[]
            for unit in j.units('p3_cases'):
                context=read(unit/'case.json')
                for file,target in [('candidate_guarantees.csv',all_candidates),('pair_bounds.csv',all_pairs),('primary_sensitivity.csv',all_sensitivity)]:
                    import csv
                    with (unit/file).open(encoding='utf-8',newline='') as f:
                        target.extend({**context,**r} for r in csv.DictReader(f))
                for approach in ('joint','rectangle','separate'):
                    local=[r for r in all_candidates[-18:] if r['approach']==approach]
                    for delta in c['delta_grid']:
                        coverage.append({**context,'approach':approach,'delta':delta,'admissible_candidates':sum(float(r['G'])<=delta for r in local),'utility_threshold_validated':False})
            table(out/'candidate_guarantees.csv',all_candidates);table(out/'pair_bounds.csv',all_pairs)
            table(out/'primary_sensitivity.csv',all_sensitivity);table(out/'delta_admissible.csv',coverage)
    print(json.dumps(read(out/'GATE.json')),flush=True);return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    with ExitStack() as guard:
        for name in ('sklearn.ensemble.HistGradientBoostingClassifier.fit','sklearn.linear_model.LogisticRegression.fit'):
            guard.enter_context(patch(name,side_effect=AssertionError('P3 forbids forecaster fits')))
        run(args.output)
