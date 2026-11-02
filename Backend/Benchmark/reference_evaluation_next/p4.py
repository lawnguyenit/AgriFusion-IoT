"""Locked new-source temporal study, cache reuse, explicit supervised-fit budget."""
from pathlib import Path
from copy import deepcopy
import argparse,json,csv
import numpy as np
import pandas as pd
import joblib
from ..reference_evaluation.contracts import MODELS,FailedSupport
from ..reference_evaluation.fitting import fit_candidates
from ..reference_evaluation.evaluation import input_fingerprints,save_inputs
from ..reference_evaluation.decisions import selection_rules,oriented_interval
from ..reference_evaluation.audit import true_risks
from ..reference_evaluation_p2.witness import trace_pool
from ..reference_evaluation_p2.validation import labels,score_witness,recheck_saved
from ..reference_evaluation_p2.persistence import save_witness
from ..reference_evaluation.storage import digest
from .journal import Journal,read,write,verify,sha
from .source235 import acquire
from .folds import prepare
from .mask_adapter import forecasts,reference_inputs
from .analysis import compare,ht,table,state_influence
from .budget import FitBudget


def fit_once(j,fold,seed,segments,canonical,base_config):
    config=deepcopy(base_config);config['study_id']=j.protocol['study_id']+'_'+fold
    signature=digest({'canonical':sha(canonical),'training_config':config['training'],'K':3,'seed':seed,'v1_code':j.context['v1_code_sha256']})
    registry_path=j.root/'FIT_REGISTRY.json';registry=read(registry_path) if registry_path.exists() else {}
    if signature in registry:
        path=Path(registry[signature]);verify(path);return path
    with j.unit('p4_fit',f'{fold}__{seed}',['fit_result.json'],[canonical]) as (out,reused):
        if not reused:
            try:
                bundle=fit_candidates(segments,config,'household235_'+fold,seed)
            except FailedSupport as exc:
                write(out/'fit_result.json',{'status':'failed_support','reason':str(exc),'fit_reuse_signature':signature})
            else:
                dev=[s for s in segments if s.partition=='development']
                public,_=forecasts(dev,bundle,'mcar30',701,fold)
                risks,_=true_risks(public,dev,3)
                default=min(risks,key=lambda r:(r['true_brier_audit'],MODELS.index(r['model'])))['model']
                bundle['development_default']=default;joblib.dump(bundle,out/'models.joblib')
                table(out/'development_risks.csv',risks)
                write(out/'fit_result.json',{'status':'complete','fit_reuse_signature':signature,'supervised_fits':4,
                       'development_default':default,'fit_metadata':bundle['fit_metadata'],'training_seed':seed,
                       'normalization_median':bundle['median'],'normalization_scale':bundle['scale']})
    registry[signature]=str(out);write(registry_path,registry);return out


def fixed_predictions(j,fold,seed,regime,fit_path,segments):
    verify(fit_path)
    with j.unit('p4_forecast',f'{fold}__{seed}__{regime}',['selection_inputs.npz','assessment_inputs.npz','mask_seeds.json'],[fit_path/'READY.json']) as (out,reused):
        if not reused:
            bundle=joblib.load(fit_path/'models.joblib');metadata=[]
            for part in ('selection','assessment'):
                reference=[s for s in segments if s.partition==part]
                public,seeds=forecasts(reference,bundle,regime,seed,fold)
                save_inputs(out/(part+'_inputs.npz'),public);metadata.extend(seeds)
            write(out/'mask_seeds.json',metadata)
    return out


def cell(j,fold,seed,regime,policy,refseed,fit_path,forecast_path,segments):
    from ..reference_evaluation.evaluation import load_inputs
    key=f'{fold}__{seed}__{regime}__{policy}__{refseed}'
    with j.unit('p4_evaluate',key,['pair_bounds.csv','candidate_guarantees.csv','selection_results.csv','model_risks.csv','point_estimates.csv','mask_ablation.csv','witnesses.json'],[fit_path/'READY.json',forecast_path/'READY.json']) as (out,reused):
        if not reused:
            verify(fit_path);verify(forecast_path);bundle=joblib.load(fit_path/'models.joblib')
            base={'dataset_id':'household235','fold':fold,'training_seed':seed,'input_regime':regime,'reference_policy':policy,'reference_seed':refseed}
            pair_rows=[];candidate_rows=[];risk_rows=[];point_rows=[];ablations=[];witnesses=[];seed_records=[];truth={}
            audit=out/'audit_only';audit.mkdir()
            for part in ('selection','assessment'):
                fixed=load_inputs(forecast_path/(part+'_inputs.npz'));reference=[s for s in segments if s.partition==part]
                public,records=reference_inputs(fixed,reference,policy,refseed,fold,seed)
                if input_fingerprints(public)!=input_fingerprints(fixed):raise AssertionError('Reference changed p/cohort')
                seed_records.extend(records);save_inputs(out/(part+'_inputs.npz'),public)
                pairs,points,candidates,decisions,risks,info=compare(public,[s.states for s in reference],bundle['transition'],bundle['prior'],bundle['state_prevalence'],3)
                if policy=='full_control' and any(abs(r['joint_upper']-r['joint_lower'])>1e-9 for r in pairs):raise AssertionError('Full-control noncollapse')
                if policy=='mcar30':points+=ht(public,3)
                # Choices read point estimates/pair bounds only; never assessment risk.
                if part=='selection':
                    public_pairs=[{k:v for k,v in r.items() if not k.endswith('_audit')} for r in pairs]
                    choices=selection_rules(public_pairs,points,bundle['development_default'])
                    choices += [{'selection_rule':'minimax_'+r['approach'],'selected_model':r['selected_model'],'certificate':'FINITE_POOL_G_BOUND'} for r in decisions]
                    if policy=='mcar30':
                        estimates=[r for r in points if r['estimator']=='HT_independent_reference_MCAR']
                        chosen=min(estimates,key=lambda r:(r['estimated_risk'],r['model']))['model']
                        choices.append({'selection_rule':'HT_independent_reference_MCAR','selected_model':chosen,'certificate':'NOT_APPLICABLE'})
                    write(out/'selection_decisions.json',choices)
                truth[part]={r['model']:r['true_brier_audit'] for r in risks}
                context={**base,'partition':part,**info}
                pair_rows.extend({**context,**r} for r in pairs);candidate_rows.extend({**context,**r} for r in candidates)
                risk_rows.extend({**base,'partition':part,**r} for r in risks);point_rows.extend({**base,'partition':part,**r} for r in points)
                n=sum(len(s.keys) for s in public);observed=sum(int((s.observed>=0).sum()) for s in public)
                scored=sum(int(s.score.sum()) for s in public)
                influence=sum(float(state_influence(s.probabilities,s.score,3)[s.observed<0].sum())*int(s.score.sum())/scored for s in public)
                plo,phi=oriented_interval(pairs,'SOFT_EM_HGB','COMPLETE_HGB')
                ablations.append({**context,'recorded_states':n,'observed_reference_states':observed,'missing_fraction':1-observed/n,
                                  'hidden_reference_count':n-observed,'hidden_I_sum':influence,'primary_joint_width':phi-plo,
                                  'p_reference_invariant':True,'full_control_collapse':policy=='full_control'})
                np.savez_compressed(audit/(part+'_truth.npz'),keys=np.concatenate([s.keys for s in reference]),F=np.concatenate([s.states for s in reference]),END=np.concatenate([labels(s.states,3) for s in reference]))
                if seed==11 and regime=='mcar30' and policy=='mcar30' and refseed==11:
                    lower,upper=oriented_interval(pairs,'SOFT_EM_HGB','COMPLETE_HGB')
                    for direction,endpoint in [('min',lower),('max',upper)]:
                        z=trace_pool(public,3,direction);result,y=score_witness(public,z,3,24,endpoint)
                        file=out/(part+'_'+direction+'_witness.npz');save_witness(file,public,z,y);recheck_saved(file,public,3,24,endpoint)
                        witnesses.append({**base,'partition':part,'direction':direction,**result,'path':file.name,'sha256':sha(file)})
            outcomes=[]
            for choice in choices:
                model=choice['selected_model'];selection=truth['selection'];assessment=truth['assessment']
                outcomes.append({**base,**choice,'selection_regret_audit':selection[model]-min(selection.values()) if model else None,
                                 'assessment_brier_audit':assessment.get(model),'assessment_regret_audit':assessment[model]-min(assessment.values()) if model else None})
            for name,values in [('pair_bounds.csv',pair_rows),('candidate_guarantees.csv',candidate_rows),('model_risks.csv',risk_rows),('point_estimates.csv',point_rows),('mask_ablation.csv',ablations),('selection_results.csv',outcomes)]:table(out/name,values)
            write(out/'witnesses.json',witnesses);write(out/'reference_mask_seeds.json',seed_records)
    return out


def run(root,attestation):
    j=Journal(root);reports=j.units('p3_report')
    if len(reports)!=1 or not read(reports[0]/'GATE.json')['open_P4']:raise ValueError('P3 gate does not permit P4')
    verify(reports[0]);c=j.protocol['confirmation'];write(j.root/'SOURCE_HISTORY_ATTESTATION.json',attestation)
    source=acquire(j);hourly=pd.read_csv(source/'canonical_hourly.csv')
    base=read(Path(__file__).parents[1]/'reference_evaluation/configs/recorded_hourly_v1.json')
    completed=[];support_all=[];skipped=[]
    with FitBudget(j.root,c['maximum_supervised_fits']) as budget:
        for fold in c['folds']:
            with j.unit('p4_audit',fold['id'],['canonical.csv','support_audit.csv','fold_manifest.json'],[source/'READY.json']) as (audit,reused):
                if not reused:
                    prepared,segments,support=prepare(hourly,fold,c);prepared.to_csv(audit/'canonical.csv',index=False)
                    table(audit/'support_audit.csv',support);write(audit/'fold_manifest.json',{'fold':fold,'support':support,'threshold_train_only':True})
            frame=pd.read_csv(audit/'canonical.csv',dtype={'sample_id':str,'entity':str,'segment_id':str,'partition':str})
            from ..reference_evaluation.preparation import segments_from_frame
            segments=segments_from_frame(frame)
            with (audit/'support_audit.csv').open(encoding='utf-8',newline='') as f:support_all.extend(csv.DictReader(f))
            for seed in c['training_seeds']:
                fit=fit_once(j,fold['id'],seed,segments,audit/'canonical.csv',base)
                result=read(fit/'fit_result.json')
                if result['status']!='complete':skipped.append({'fold':fold['id'],'seed':seed,'reason':result});continue
                for regime in c['input_regimes']:
                    frozen=fixed_predictions(j,fold['id'],seed,regime,fit,segments)
                    refs=[('full_control',0)]+[(policy,rs) for policy in ('mcar30','block30') for rs in c['reference_seeds']]
                    for policy,rs in refs:
                        unit=cell(j,fold['id'],seed,regime,policy,rs,fit,frozen,segments);completed.append(unit)
                        if len(completed)%7==0:print(f'P4 {len(completed)}/126 cells; actual supervised fits={budget.record["attempted"]}',flush=True)
    from .p4_report import report
    return report(j,completed,support_all,skipped)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--history',choices=['not_used','used_or_unknown'],default='used_or_unknown');a=p.parse_args()
    run(a.output,{'user_history':a.history,'interpretation':'protocol-locked new-source confirmation' if a.history=='not_used' else 'protocol-locked extension; prior source-outcome independence unverified'})
