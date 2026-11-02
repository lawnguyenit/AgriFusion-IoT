"""Locked no-refit pilot. Run as a module from the resolved repo root."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import shutil
from unittest.mock import patch
import numpy as np
from ..reference_evaluation.contracts import MODELS
from ..reference_evaluation.evaluation import input_fingerprints, save_inputs
from ..reference_evaluation.fitting import make_inputs
from ..reference_evaluation.decisions import oriented_interval
from .evidence import Evidence, sha
from .mask_roles import forecast, attach_reference
from .witness import primary_bounds, trace_pool, PAIR
from .validation import audit_delta, score_witness, classify, recheck_saved
from .persistence import json_file, csv_file, save_witness, manifest

LOCK = {'schema_version':'p2_pilot_r0_v1','sources':['beijing_multi_site_501','appliances_energy_374'],
        'training_seed':11,'feature_seed':11,'reference_seeds':[11,22],
        'policies':['mcar30','block30'],'partitions':['selection','assessment'],
        'witness_cases':'all eight original shared-mask cases, not selected by endpoints',
        'pair':list(PAIR),'K':3,'global_R':0,'warmup':24,'no_refit':True,
        'numerical_tolerance':1e-12,'endpoint_validation_tolerance':1e-9,
        'scientific_scope':'correctness pilot only; no search, population or future-ranking claim'}


def evaluate_case(out, name, inputs, reference, seeds, k, warmup):
    path = out/name; path.mkdir()
    # Evaluate first, then join audit reference downstream.
    lower, upper = primary_bounds(inputs,k)
    ph,ch = input_fingerprints(inputs)
    save_inputs(path/'public_inputs.npz',inputs)
    delta = audit_delta(inputs,reference,k,warmup)
    if not lower-1e-9 <= delta <= upper+1e-9:
        raise AssertionError('Audit truth outside R0 interval')
    json_file(path/'mask_seeds.json',seeds)
    audit = path/'audit_only'; audit.mkdir()
    from .validation import labels
    np.savez_compressed(audit/'truth.npz',keys=np.concatenate([s.keys for s in reference]),
                        F=np.concatenate([s.states for s in reference]),
                        END=np.concatenate([labels(s.states,k) for s in reference]))
    return {'branch_case':name,'model_a':PAIR[0],'model_b':PAIR[1],
            'lower':lower,'upper':upper,'audit_delta':delta,
            'prediction_sha256':ph,'cohort_sha256':ch,
            'input_sha256':sha(path/'public_inputs.npz'),
            'n_scored':sum(int(s.score.sum()) for s in inputs),'R_global':0}


def run(repo, destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Choose a new P2 output directory; existing evidence is immutable')
    evidence=Evidence(repo)
    if destination.is_relative_to(evidence.root):
        raise ValueError('P2 output must be outside the immutable v1 output tree')
    if evidence.config['time_grid_and_target']['K'] != LOCK['K'] or evidence.config['time_grid_and_target']['warmup_per_segment'] != LOCK['warmup']:
        raise ValueError('P2 pilot target/warmup differs from locked v1')
    destination.mkdir(parents=True)
    json_file(destination/'P2_LOCK.json',LOCK)
    code=Path(__file__).parent; snapshot=destination/'p2_source'; snapshot.mkdir()
    for p in code.rglob('*'):
        if p.is_file() and p.suffix in {'.py','.md'} and '__pycache__' not in p.parts:
            target=snapshot/p.relative_to(code); target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,target)
    json_file(destination/'v1_config.resolved.json',evidence.config)
    rows=[]; witnesses=[]; invariance=[]; cache_checks=[]
    k,warmup=LOCK['K'],LOCK['warmup']
    for source in LOCK['sources']:
        reference,bundle=evidence.source(source)
        for partition in LOCK['partitions']:
            ref=reference[partition]
            complete,_=evidence.inputs(source,'full_control',0,partition)
            regenerated,_=make_inputs(ref,bundle,evidence.config,source,'full_control',0)
            if input_fingerprints(regenerated) != input_fingerprints(complete):
                raise AssertionError('Cache cannot reproduce frozen full-control predictions/cohort')
            cache_checks.append({'source':source,'partition':partition,'cache_full_control_prediction_match':True})
            for policy in LOCK['policies']:
                case=f'{source}__11__{policy}__11__{partition}'
                shared,unit=evidence.inputs(source,policy,11,partition)
                if input_fingerprints(shared)[1] != input_fingerprints(complete)[1]:
                    raise AssertionError('Full/shared cohorts differ')
                d=evaluate_case(destination,case+'__D',shared,ref,[],k,warmup)
                import csv
                with (unit/'pair_bounds.csv').open(encoding='utf-8',newline='') as f:
                    old=[r for r in csv.DictReader(f) if r['partition']==partition]
                old=[{**r,'joint_lower':float(r['joint_lower']),'joint_upper':float(r['joint_upper'])} for r in old]
                low,high=oriented_interval(old,*PAIR)
                if max(abs(d['lower']-low),abs(d['upper']-high))>1e-9:
                    raise AssertionError('Primary DP does not reproduce old interval')
                rows.append(d)
                for direction,endpoint in [('min',low),('max',high)]:
                    z=trace_pool(shared,k,direction)
                    result,ys=score_witness(shared,z,k,warmup,endpoint)
                    path=destination/(case+'__D')/(direction+'_witness.npz')
                    save_witness(path,shared,z,ys)
                    reloaded=recheck_saved(path,shared,k,warmup,endpoint)
                    witnesses.append({'case':case,'direction':direction,**result,
                                      'saved_witness_rechecked':reloaded,'witness_sha256':sha(path),
                                      'original_input_path':str(unit/(partition+'_inputs.npz')),
                                      'original_input_sha256':sha(unit/(partition+'_inputs.npz')),
                                      'prediction_sha256':d['prediction_sha256'],
                                      'cohort_sha256':d['cohort_sha256'],
                                      'interpretation':classify(low,high,LOCK['numerical_tolerance'],result['endpoint_absolute_error'])})
                attained=witnesses[-2:]
                interpretation=classify(attained[0]['objective'],attained[1]['objective'],
                                        LOCK['numerical_tolerance'],max(w['endpoint_absolute_error'] for w in attained))
                for w in attained:
                    w['interpretation']=interpretation
                masked,feature_seeds=forecast(ref,bundle,policy,11,source,k,warmup)
                b,bseeds=attach_reference(masked,ref,policy,0,source,warmup,full=True)
                b_row=evaluate_case(destination,case+'__B',b,ref,feature_seeds+bseeds,k,warmup)
                if abs(b_row['upper']-b_row['lower'])>1e-9:
                    raise AssertionError('Full reference did not collapse')
                rows.append(b_row)
                baseline_hash=input_fingerprints(complete)
                masked_hash=input_fingerprints(masked)
                for seed in LOCK['reference_seeds']:
                    for branch,base,expected,feature_metadata in [('A',complete,baseline_hash,[]),('C',masked,masked_hash,feature_seeds)]:
                        public,rseeds=attach_reference(base,ref,policy,seed,source,warmup)
                        if input_fingerprints(public)!=expected:
                            raise AssertionError('Reference seed changed fixed p/cohort')
                        row=evaluate_case(destination,case+f'__{branch}__reference{seed}',public,ref,feature_metadata+rseeds,k,warmup)
                        rows.append(row); invariance.append({'case':case,'branch':branch,'reference_seed':seed,
                                                             'prediction_cohort_invariant':True,
                                                             'prediction_sha256':expected[0],'cohort_sha256':expected[1]})
                print('completed '+case,flush=True)
    evidence.unchanged()
    csv_file(destination/'mask_ablation.csv',rows);csv_file(destination/'witness_index.csv',witnesses)
    json_file(destination/'provenance.json',{'repo':str(evidence.repo),'original_report':str(evidence.report),
              'v1_manifest':__import__('json').loads((evidence.report/'run_manifest.json').read_text()),
              'old_file_hashes':evidence.hashes,'P2_LOCK':LOCK,'all_original_files_unchanged':True,
              'environment':evidence.environment,'command':__import__('sys').argv,'cwd':str(Path.cwd())})
    json_file(destination/'validation.json',{'status':'passed','new_model_fits':0,'fit_methods_guarded':True,
              'witness_cases':8,'endpoint_witnesses':len(witnesses),'mask_ablation_rows':len(rows),
              'reference_invariance_checks':invariance,'cache_prediction_checks':cache_checks,
              'same_cohort':True,'audit_containment':True,'B_full_control_collapse':True,
              'original_D_intervals_reproduced':True,'all_saved_witnesses_rechecked':True,
              'R_scope':0,'numerics':'float extrema/witness checks within tolerance, not exact arithmetic proof',
              'limitations':['Appliances limited_support','No future-ranking or novelty claim','R>0 traceback not implemented']})
    (destination/'P2_SUMMARY.md').write_text(
        '# P2 pilot — passed\n\nEight predeclared cases,16 primary-pair endpoint witnesses;48 A/B/C/D rows. '
        'Reference-only seed changes preserve all six predictions/cohort. B full-reference bounds collapse; '
        'audit truth is contained; D reproduces old intervals. Project cache reproduces full-control forecasts. '
        'No fit, hyperparameter search, target/split/pool changes or v1 mutation.\n\n'
        'Read witness_index.csv for attained endpoints and strict-order/tie/numerical classifications. '
        'Witness NPZs contain every key/state/derived END and segment offsets; no hypothetical completion is an observed truth. '
        'public_inputs.npz is the evaluator contract; audit_only/truth.npz is joined downstream only. '
        'A uses unmasked recorded forecasts; B has fixed role-separated feature mask/full reference; C freezes B '
        'and independently masks reference; D retains old shared masks. p may differ across A versus B/C versus D; '
        'invariance only applies when reference seed alone changes.\n\n'
        'This pilot implements R=0 only. Witness arithmetic is float-validated, not an exact arithmetic proof; '
        'zero endpoints and unresolved numerical margins are reported separately. No implementation/publication efficacy claim. '
        'Appliances remains limited_support. No P3/P4 execution.\n',encoding='utf-8')
    manifest(destination)
    return destination


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    with ExitStack() as guard:
        for name in ('sklearn.ensemble.HistGradientBoostingClassifier.fit','sklearn.linear_model.LogisticRegression.fit',
                     'Backend.Benchmark.reference_evaluation.fitting.fit_candidates'):
            guard.enter_context(patch(name,side_effect=AssertionError('P2 forbids model fitting')))
        print(run(args.repo,args.output))


if __name__=='__main__':
    main()
