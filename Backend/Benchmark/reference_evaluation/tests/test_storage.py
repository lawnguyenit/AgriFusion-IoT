from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from ..storage import RunStore, verify_ready


class StorageTests(unittest.TestCase):
    def make_store(self,path,resume=False):
        return RunStore(path,{'study_id':'test_only'},argv=['test-command'],resume=resume)

    def complete(self,store,stage,key,parents=()):
        with store.unit(stage,key,parents=parents) as run:
            if not run.reused:
                (run.path/'payload.txt').write_text('real payload',encoding='utf-8')
                run.accept(['payload.txt'],{'ok':True},'Test-only unit, no scientific result.')
        return run

    def test_resume_preserves_completed_bytes_and_detects_tampering(self):
        with TemporaryDirectory() as td:
            store=self.make_store(td);first=self.complete(store,'a','key')
            ready=(first.path/'READY.json').read_bytes()
            resumed=self.complete(self.make_store(td,True),'a','key')
            self.assertTrue(resumed.reused);self.assertEqual((resumed.path/'READY.json').read_bytes(),ready)
            (first.path/'payload.txt').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'changed/missing'):
                self.make_store(td,True).unit('a','key')

    def test_unaccepted_outputs_never_get_READY(self):
        with TemporaryDirectory() as td:
            store=self.make_store(td)
            with self.assertRaises(RuntimeError):
                with store.unit('broken','x') as run:
                    run.accept(['missing.bin'],{},'Missing output test')
            self.assertFalse((run.path/'READY.json').exists())
            self.assertEqual(json.loads((run.path/'run_manifest.json').read_text())['execution_status'],'failed')

    def test_changed_config_refuses_mixed_root(self):
        with TemporaryDirectory() as td:
            self.make_store(td)
            with self.assertRaisesRegex(ValueError,'Config changed'):
                RunStore(td,{'study_id':'a_different_profile'})

    def test_replacing_parent_invalidates_pointers_not_old_evidence(self):
        with TemporaryDirectory() as td:
            root=Path(td);raw=root/'input.txt';raw.write_text('version1')
            store=self.make_store(root/'runs')
            parent=self.complete(store,'audit','source',[raw])
            child=self.complete(store,'fit','source_seed',[parent.path/'READY.json'])
            self.assertEqual(store.active_units('fit'),[child.path])
            # Reusing the same parent must NOT invalidate the existing child.
            store.resume=True;self.complete(store,'audit','source',[raw])
            self.assertEqual(store.active_units('fit'),[child.path])
            raw.write_text('version2')
            newer=self.complete(store,'audit','source',[raw])
            self.assertNotEqual(parent.path,newer.path)
            self.assertEqual(store.active_units('fit'),[])
            self.assertTrue((child.path/'READY.json').exists())

    def test_retry_failed_unit_uses_new_attempt_and_keeps_traceback(self):
        with TemporaryDirectory() as td:
            store=self.make_store(td)
            with self.assertRaises(ValueError):
                with store.unit('a','x') as first:raise ValueError('deliberate failure')
            second=self.complete(self.make_store(td,True),'a','x')
            self.assertNotEqual(first.path,second.path)
            self.assertIn('deliberate failure',(first.path/'stderr.log').read_text())
            self.assertTrue((second.path/'READY.json').exists())

    def test_failed_replacement_cannot_leave_stale_parent_active(self):
        with TemporaryDirectory() as td:
            raw=Path(td)/'raw.txt';raw.write_text('v1')
            store=self.make_store(Path(td)/'runs')
            parent=self.complete(store,'audit','source',[raw])
            child=self.complete(store,'fit','source_seed',[parent.path/'READY.json'])
            raw.write_text('v2');store.resume=True
            with self.assertRaises(ValueError):
                with store.unit('audit','source',parents=[raw]):raise ValueError('new source audit failed')
            self.assertEqual(store.active_units('audit'),[])
            self.assertEqual(store.active_units('fit'),[])
            self.assertTrue((parent.path/'READY.json').exists() and (child.path/'READY.json').exists())
