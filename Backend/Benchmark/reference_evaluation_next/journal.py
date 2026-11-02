"""New study units, frozen protocol/source inventory, explicit failure receipts."""
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil,traceback,sys
from ..reference_evaluation.storage import digest,environment,code_snapshot


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n',encoding='utf-8')
    tmp.replace(p)


def verify(path):
    ready=read(Path(path)/'READY.json')
    for f in ready['files']:
        p=Path(path)/f['path']
        if not p.is_file() or p.stat().st_size!=f['bytes'] or sha(p)!=f['sha256']:
            raise ValueError('Immutable unit mismatch '+str(p))
    return ready


class Journal:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        source=Path(__file__).parent;self.protocol=read(source/'protocol.json')
        lock=self.root/'PROTOCOL_LOCK.json'
        if lock.exists() and read(lock)!=self.protocol:raise ValueError('Protocol changed; new output root required')
        if not lock.exists():write(lock,self.protocol)
        inventory=[{'path':p.relative_to(source).as_posix(),'sha256':sha(p)} for p in sorted(source.rglob('*')) if p.is_file() and p.suffix in {'.py','.json'} and '__pycache__' not in p.parts]
        self.context={'protocol_sha256':digest(self.protocol),'code_sha256':digest(inventory),'v1_code_sha256':code_snapshot()[0]['sha256'],'environment':environment()}
        snap=self.root/'source_snapshots'/self.context['code_sha256']
        if not snap.exists():
            for f in inventory:
                p=snap/f['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/f['path'],p)
            write(snap/'SNAPSHOT.json',{'inventory':inventory,**self.context})

    @contextmanager
    def unit(self,stage,key,required,parents=()):
        inputs=[{'path':str(Path(p).resolve()),'sha256':sha(p)} for p in parents]
        signature=digest({'context':self.context,'stage':stage,'key':key,'inputs':inputs})
        path=self.root/stage/(key+'__'+signature[:16]);path.mkdir(parents=True,exist_ok=True)
        if (path/'READY.json').exists():
            verify(path);yield path,True;return
        if (path/'receipt.json').exists():raise RuntimeError('Retain failed/interrupted unit; choose a fresh explicitly documented attempt root')
        record={'stage':stage,'key':key,'signature':signature,**self.context,'inputs':inputs,'status':'running','argv':sys.argv,'cwd':str(Path.cwd()),'started_at_utc':datetime.now(timezone.utc).isoformat()}
        write(path/'receipt.json',record)
        try:
            with (path/'stdout.log').open('w',encoding='utf-8') as out,(path/'stderr.log').open('w',encoding='utf-8') as err,redirect_stdout(out),redirect_stderr(err):
                yield path,False
            missing=[n for n in required if not (path/n).is_file()]
            if missing:raise ValueError('Missing outputs '+str(missing))
            record.update(status='complete',return_code=0,finished_at_utc=datetime.now(timezone.utc).isoformat())
            write(path/'receipt.json',record)
            files=[{'path':p.relative_to(path).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(path.rglob('*')) if p.is_file() and p.name!='READY.json']
            write(path/'READY.json',{'signature':signature,'files':files})
        except BaseException as exc:
            record.update(status='failed',return_code=1,error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
            write(path/'receipt.json',record);raise

    def units(self,stage):
        return [p.parent for p in sorted((self.root/stage).glob('*/READY.json'))]
