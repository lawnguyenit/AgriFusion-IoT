"""Load only project-owned artifacts after READY and source verification."""
from pathlib import Path
import hashlib
import json
import joblib
import pandas as pd
from ..reference_evaluation.storage import code_snapshot, environment, digest
from ..reference_evaluation.contracts import MODELS
from ..reference_evaluation.preparation import segments_from_frame
from ..reference_evaluation.evaluation import load_inputs


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


class Evidence:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        self.root = self.repo/'Backend/Output_data/reference_evaluation'
        self.graph = read(self.root/'ACTIVE_GRAPH.json'); self.hashes = {}
        self.checked(self.root/'ACTIVE_GRAPH.json')
        self.report = self.unit('report:current_graph')
        if self.report.name != 'current_graph__71b84c1ff33cc2a3':
            raise ValueError('P2 pilot is locked to the P1-verified report')
        self.config = read(self.report/'config.resolved.json')
        if code_snapshot()[0]['sha256'] != read(self.report/'run_manifest.json')['code_sha256']:
            raise ValueError('v1 source changed since P1')
        self.environment=environment()
        if digest(self.environment) != read(self.report/'run_manifest.json')['environment_sha256']:
            raise ValueError('Use the original environment with recorded thread limits=2')
        self.checked(self.root/'p1_audit_20261102/validation.json')
        p1 = read(self.root/'p1_audit_20261102/validation.json')
        if not p1.get('P1_pass'):
            raise ValueError('P1 gate is not passed')

    def checked(self, path):
        path = Path(path); value = sha(path)
        self.hashes[str(path)] = value
        return value

    def unit(self, key):
        path = self.root/self.graph[key]['relative_path']
        ready = read(path/'READY.json'); self.checked(path/'READY.json')
        for item in ready['files']:
            p = path/item['path']
            if p.stat().st_size != item['bytes'] or self.checked(p) != item['sha256']:
                raise ValueError('Changed READY artifact: '+str(p))
        return path

    def source(self, source):
        audit = self.unit('audit:'+source); fit = self.unit('fit:'+source+'__11')
        frame = pd.read_csv(audit/'canonical.csv',dtype={'sample_id':str,'entity':str,'segment_id':str,'partition':str})
        # This exact cache has just passed its project-generated READY hash.
        bundle = joblib.load(fit/'models.joblib')
        if tuple(bundle['model_order']) != MODELS or bundle['training_mask_seed'] != 11:
            raise ValueError('Wrong locked fit cache')
        reference = {part:segments_from_frame(frame,part) for part in ('selection','assessment')}
        return reference,bundle

    def inputs(self, source, policy, seed, partition):
        unit = self.unit(f'evaluate:{source}__11__{policy}__{seed}')
        return load_inputs(unit/(partition+'_inputs.npz')),unit

    def unchanged(self):
        if any(sha(p) != value for p,value in self.hashes.items()):
            raise ValueError('An original artifact changed during P2')
