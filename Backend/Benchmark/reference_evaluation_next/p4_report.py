"""Evidence-preserving P4 aggregation, held-out contrasts and baseline comparisons."""
import csv
import numpy as np
from .journal import read,write,verify
from .analysis import table


def rows(path):
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def report(j,units,support,skipped):
    required=['STUDY_SUMMARY.json','support_audit.csv','pair_bounds.csv','candidate_guarantees.csv','selection_results.csv','mechanism_transfer.csv']
    with j.unit('p4_report','locked_confirmation',required,[p/'READY.json' for p in units]) as (out,reused):
        if not reused:
            supported={fold['id']:all(r['status']=='adequate_for_declared_support_gate' for r in support if r['fold']==fold['id'] and r['partition'] in ('selection','assessment')) for fold in j.protocol['confirmation']['folds']}
            collected={}
            for name in ['pair_bounds.csv','candidate_guarantees.csv','selection_results.csv','model_risks.csv','point_estimates.csv','mask_ablation.csv']:
                values=[]
                for p in units:
                    verify(p)
                    values.extend({**r,'fold_support_adequate':supported[r['fold']]} for r in rows(p/name))
                collected[name]=values;table(out/name,values)
            table(out/'support_audit.csv',support)
            witnesses=[]
            for p in units:witnesses.extend({**r,'source_run':str(p)} for r in read(p/'witnesses.json'))
            table(out/'witness_index.csv',witnesses)
            ablations=collected['mask_ablation.csv'];contrasts=[]
            from itertools import product
            for fold,seed,regime,part in product(['F1','F2','F3'],[11,22,33],['full','mcar30'],['selection','assessment']):
                group=[r for r in ablations if r['fold']==fold and int(r['training_seed'])==seed and r['input_regime']==regime and r['partition']==part and r['reference_policy']=='block30']
                if len(group)!=3:continue
                high=sorted(group,key=lambda r:(-float(r['hidden_I_sum']),int(r['reference_seed'])))[0]
                low=sorted(group,key=lambda r:(float(r['hidden_I_sum']),int(r['reference_seed'])))[0]
                if high['prediction_sha256']!=low['prediction_sha256'] or high['cohort_sha256']!=low['cohort_sha256'] or high['hidden_reference_count']!=low['hidden_reference_count']:raise AssertionError('Unmatched transfer contrast')
                effect=float(high['primary_joint_width'])-float(low['primary_joint_width'])
                contrasts.append({'fold':fold,'training_seed':seed,'input_regime':regime,'partition':part,
                                  'high_reference_seed':high['reference_seed'],'low_reference_seed':low['reference_seed'],
                                  'I_high_minus_low':float(high['hidden_I_sum'])-float(low['hidden_I_sum']),
                                  'joint_width_high_minus_low':effect,'counterexample':effect < -1e-12,'fold_support_adequate':supported[fold]})
            table(out/'mechanism_transfer.csv',contrasts)
            transfer={}
            for part in ('selection','assessment'):
                data=[r for r in contrasts if r['partition']==part and r['fold_support_adequate']]
                effects=[r['joint_width_high_minus_low'] for r in data]
                transfer[part]={'contrasts':len(data),'median_effect':float(np.median(effects)) if effects else None,
                                'mean_effect':float(np.mean(effects)) if effects else None,
                                'counterexamples':sum(r['counterexample'] for r in data),'ties':sum(abs(v)<=1e-12 for v in effects)}
            outcomes=collected['selection_results.csv'];baseline=[]
            for fold in ('F1','F2','F3'):
                group=[r for r in outcomes if r['fold']==fold and r['assessment_regret_audit']!='']
                for scope in ('all_reference_cases','missing_reference_only'):
                    subset=[r for r in group if scope=='all_reference_cases' or r['reference_policy']!='full_control']
                    for rule in sorted({r['selection_rule'] for r in subset}):
                        data=[r for r in subset if r['selection_rule']==rule]
                        baseline.append({'fold':fold,'scope':scope,'selection_rule':rule,'cells':len(data),
                                         'mean_assessment_regret':float(np.mean([float(r['assessment_regret_audit']) for r in data])),
                                         'mean_assessment_brier':float(np.mean([float(r['assessment_brier_audit']) for r in data])),
                                         'fold_support_adequate':supported[fold]})
            table(out/'baseline_assessment.csv',baseline)
            covariance=[]
            for fold in ('F1','F2','F3'):
                for scope in ('all_reference_cases','missing_reference_only'):
                    base={r['selection_rule']:r for r in baseline if r['fold']==fold and r['scope']==scope}
                    if 'minimax_joint' not in base:continue
                    for name in ('development_only','always_SOFT_EM_HGB','always_COMPLETE_HGB'):
                        if name in base:covariance.append({'fold':fold,'scope':scope,'baseline':name,'joint_minus_baseline_assessment_regret':base['minimax_joint']['mean_assessment_regret']-base[name]['mean_assessment_regret'],'fold_support_adequate':supported[fold]})
            table(out/'paired_baseline_differences.csv',covariance)
            sufficient=all(transfer[p]['median_effect'] is not None and transfer[p]['median_effect']>1e-12 for p in transfer)
            budget=read(j.root/'SUPERVISED_FIT_BUDGET.json')
            if budget['attempted']>36:raise AssertionError('Budget exceeded')
            summary={'execution_status':'complete' if len(units)==126 else 'incomplete_support_failures','evaluation_cells':len(units),'expected_cells':126,
                     'supervised_fit_attempts':budget['attempted'],'maximum_supervised_fits':36,'skipped_fit_support':skipped,
                     'source_history':read(j.root/'SOURCE_HISTORY_ATTESTATION.json'),'supported_folds':supported,
                     'mechanism_transfer':transfer,'directional_transfer_supported':sufficient,
                     'future_action_superiority_claim':False,'physical_event_truth':False,'new_method_claim':False,
                     'interpretation':'Report mechanism transfer and held-out losses separately. Shared source/folds/masks are dependent; no pseudo-independent p-values.',
                     'numerical_tolerance':1e-12,'endpoint_validation_tolerance':1e-9,'retained_baselines':sorted({r['selection_rule'] for r in outcomes})}
            write(out/'STUDY_SUMMARY.json',summary)
    print(__import__('json').dumps(read(out/'STUDY_SUMMARY.json')),flush=True);return out
