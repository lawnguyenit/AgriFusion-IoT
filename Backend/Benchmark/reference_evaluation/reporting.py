"""Aggregate current validated graph only; preserve old attempts outside it."""
from pathlib import Path
import json
import shutil
import pandas as pd
from .config import cells
from .contracts import MODELS
from .storage import atomic_json, atomic_csv, sha256, now, verify_ready

TABLES = {"audit":["support_audit.csv"], "evaluate":["pair_bounds.csv","model_risks.csv","selection_results.csv","mask_summary.csv"],
          "sensitivity":["reference_error_sensitivity.csv","synthetic_corruption.csv"], "solver":["generic_solver_results.csv"]}


def write_report(store):
    parents = store.active_units()
    parents = [p for p in parents if json.loads((p/'run_manifest.json').read_text())["stage"] not in ("report",)]
    if not parents:
        raise FileNotFoundError("No current-code validated units to report")
    with store.unit("report", "current_graph", parents=[p/'READY.json' for p in parents]) as run:
        if not run.reused:
            collected = {}
            for stage, names in TABLES.items():
                for name in names:
                    frames = []
                    for p in store.active_units(stage):
                        if (p/name).exists():
                            frame = pd.read_csv(p/name)
                            if len(frame):
                                frame["source_run_id"] = p.name; frames.append(frame)
                    data = pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=["status"])
                    data.to_csv(run.path/name,index=False); collected[name] = data
            risk = collected["model_risks.csv"]
            dominance = []
            if len(risk):
                grouping = ["dataset_id","training_mask_seed","partition","policy","mask_seed"]
                minima=risk.groupby(grouping).true_brier_audit.transform('min')
                winners=risk.loc[(risk.true_brier_audit-minima).abs()<=store.config['comparison']['numerical_tolerance']]
                for (source,part,model),g in winners.groupby(["dataset_id","partition","model"]):
                    dominance.append({"dataset_id":source,"partition":part,"model":model,"co_winner_cells":len(g),
                                      "tie_policy":"include all candidates within declared tolerance",
                                      "interpretation":"mask cells on shared data, not independent studies"})
            run.csv("fixed_model_winner_counts.csv",dominance,
                    None if dominance else ["dataset_id","partition","model","co_winner_cells","tie_policy","interpretation"])
            pairs = collected["pair_bounds.csv"]; certs = []
            if len(pairs):
                keys = ["dataset_id","partition","model_a","model_b"]
                for group,g in pairs.groupby(keys,sort=False):
                    for method in ("joint","rectangle","separate"):
                        left,right=g[method+"_lower"],g[method+"_upper"]
                        tol=store.config['comparison']['numerical_tolerance']
                        certs.append({**dict(zip(keys,group)),"method":method,"comparisons":len(g),
                                      "A_BETTER":int((right < -tol).sum()),"B_BETTER":int((left > tol).sum()),
                                      "INCONCLUSIVE":int(((right >= -tol)&(left <= tol)).sum())})
            run.csv("certificate_summary.csv",certs,
                    None if certs else ["dataset_id","partition","model_a","model_b","method","comparisons","A_BETTER","B_BETTER","INCONCLUSIVE"])
            planned_cases = len(store.config['sources'])*len(store.config['training']['training_mask_seeds'])*len(list(cells(store.config)))
            complete_cases = len(store.active_units("evaluate"))
            expected_solves = store.config['generic_solver']['expected_solve_count_if_both_sources_pass']
            full_P2 = any(json.loads((p/'metrics.json').read_text()).get('full_P2_gate',False) for p in store.active_units('validate'))
            smoke_passed = bool(store.active_units('smoke'))
            metrics={"completed_evaluation_cells":complete_cases,"planned_evaluation_cells":planned_cases,
                     "complete_generic_solves":len(store.active_units('solver')),"planned_generic_solves":expected_solves,
                     "full_P2_gate":full_P2,"local_smoke_completed":smoke_passed,
                     "full_plan_complete":full_P2 and smoke_passed and complete_cases==planned_cases and len(store.active_units('sensitivity'))==planned_cases and len(store.active_units('solver'))==expected_solves,
                     "masks_are_independent_studies":False,"new_algorithm_claim":False}
            summary=(f"# Current study checkpoint\n\nEvaluation cells completed: {complete_cases}/{planned_cases}. "
                     f"Generic solves recorded: {metrics['complete_generic_solves']}/{expected_solves}.\n"
                     f"Full predeclared plan completed: {metrics['full_plan_complete']}.\n\n"
                     "Inspect support before interpreting results. Fixed-model baselines, fallback choices and inconclusive verdicts are separate. "
                     "Selection finite-pool regret and later-assessment regret are distinct. A mask/site/seed is not an independent source.\n\n"
                     "Tables are collected only from the current validated dependency graph; older failed attempts remain in RUN_INDEX.csv. "
                     "No physical-reference validation, general future guarantee or new-method claim is established by this checkpoint.\n")
            run.accept(["pair_bounds.csv","selection_results.csv","certificate_summary.csv"],metrics,summary)
    (store.root/'STUDY_STATUS.md').write_text((run.path/'SUMMARY.md').read_text(encoding='utf-8'),encoding='utf-8')
    atomic_json(store.root/'SOURCE_INDEX.json',[{"path":str(p.relative_to(store.root)),
                 "source_inventory_path":str((p/'source_inventory.json').relative_to(store.root))} for p in store.active_units('audit')])
    return run.path


def export_sync_tree(store, without_audit_truth=False):
    """Create a stable mirror for desktop/manual Drive sync; never claim upload."""
    target = store.root/'drive_sync'; target.mkdir(exist_ok=True)
    sources=[]
    for name in ('STUDY_STATUS.md','RUN_INDEX.csv','ARTIFACT_INDEX.csv','SOURCE_INDEX.json','LATEST.json','ACTIVE_GRAPH.json','STUDY_LOCK.json','BLOCKERS.json'):
        if (store.root/name).exists():sources.append((store.root/name,True))
    for unit in store.active_units():
        declared = verify_ready(unit)['files']
        for relative in [item['path'] for item in declared]+['READY.json']:
            file=unit/relative
            if file.is_file() and (not without_audit_truth or 'audit_only' not in file.relative_to(unit).parts):
                sources.append((file,False))
    code=store.root/'code_snapshots'/store.code['sha256']
    sources.extend((p,False) for p in code.rglob('*') if p.is_file())
    # Only finished CLI receipts are exported. The currently running export has no exit code yet.
    for receipt in (store.root/'invocations').glob('*.json'):
        if json.loads(receipt.read_text()).get('return_code') is not None:sources.append((receipt,False))
    # Preserve public source provenance/checksums once, without copying big raw archives.
    sources.extend((p,False) for p in (store.root/'raw').glob('*/**/raw_manifest.json'))
    files=[]; copied=0
    for source,mutable in sources:
        relative=source.relative_to(store.root); dest=target/relative; checksum=sha256(source)
        if dest.exists() and sha256(dest)!=checksum and not mutable:
            raise ValueError(f'Immutable export artifact changed: {relative}')
        if not dest.exists() or sha256(dest)!=checksum:
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_name(dest.name+'.partial');shutil.copyfile(source,temp);temp.replace(dest);copied+=1
        files.append({'path':relative.as_posix(),'bytes':source.stat().st_size,'sha256':checksum})
    atomic_json(target/'EXPORT_MANIFEST.json',{'created_at_utc':now(),'files':files,'files_copied_this_call':copied,
                'audit_truth_included':not without_audit_truth,'uploaded_to_drive':False,'drive_urls_verified':False,
                'instruction':'Sync this tree to the user-owned Drive results folder, then attach actual upload receipts/URLs.'})
    (target/'SYNC_README.md').write_text('This is a local export, not a verified Drive upload. Sync readable indexes and new immutable files.\n'
                                        'Existing obsolete files may remain in the mirror; ACTIVE_GRAPH.json and EXPORT_MANIFEST.json identify the current evidence.\n',encoding='utf-8')
    return target
