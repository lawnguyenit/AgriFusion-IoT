"""Write only new P2 output, keeping witnesses and audit truth separate."""
import csv
import json
from pathlib import Path
import numpy as np
from .evidence import sha


def json_file(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def csv_file(path,rows):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w = csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)


def save_witness(path,inputs,completions,derived):
    offsets = np.r_[0,np.cumsum([len(s.keys) for s in inputs])]
    np.savez_compressed(path, schema_version=np.array('p2_witness_r0_v1'),
                        keys=np.concatenate([s.keys for s in inputs]),
                        states=np.concatenate(completions),END=np.concatenate(derived),
                        observed=np.concatenate([s.observed for s in inputs]),
                        score=np.concatenate([s.score for s in inputs]),offsets=offsets,
                        segment_ids=np.array([s.segment_id for s in inputs]))


def manifest(root):
    root=Path(root)
    json_file(root/'P2_READY.json',{'scope':'separate P2 correctness pilot; not v1 READY replacement',
              'files':[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
                       for p in sorted(root.rglob('*')) if p.is_file() and p.name!='P2_READY.json']})
