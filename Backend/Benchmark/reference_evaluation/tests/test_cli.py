from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
from ..main import main


class CLITests(unittest.TestCase):
    def test_interrupt_records_actual_130_exit_for_resumption(self):
        config=Path(__file__).parents[1]/'configs/recorded_hourly_v1.json'
        with TemporaryDirectory() as td:
            with patch('Backend.Benchmark.reference_evaluation.pipeline.Pipeline.validate',side_effect=KeyboardInterrupt):
                code=main(['validate','--unit-only','--config',str(config),'--output-root',td])
            self.assertEqual(code,130)
            receipts=list((Path(td)/'invocations').glob('*.json'))
            self.assertEqual(len(receipts),1)
            self.assertEqual(json.loads(receipts[0].read_text())['return_code'],130)
