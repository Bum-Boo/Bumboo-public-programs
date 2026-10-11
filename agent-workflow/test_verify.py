import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import verify


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'source.txt'; self.source.write_text('original')
        self.spec = self.root / 'spec.json'

    def make(self, code, **extra):
        check = dict(id='observable', claim='Observe the command result', command=[sys.executable, '-c', code],
                     cwd=str(self.root), sources=[str(self.source)], **extra)
        self.spec.write_text(json.dumps(dict(goal='Validate evidence integrity', checks=[check])))
        return self.root / 'out'

    def test_pass_stales_after_source_or_log_change(self):
        out = self.make('print("observed")')
        self.assertTrue(verify.run(self.spec, out)['passed'])
        self.assertTrue(verify.fresh(out / 'result.json'))
        self.source.write_text('changed')
        self.assertFalse(verify.fresh(out / 'result.json'))
        self.source.write_text('original'); (out / 'observable.log').write_text('forged')
        self.assertFalse(verify.fresh(out / 'result.json'))

    def test_failure_and_timeout_do_not_pass(self):
        out = self.make('raise SystemExit(7)')
        value = verify.run(self.spec, out)
        self.assertFalse(value['passed']); self.assertEqual(value['checks'][0]['exit_code'], 7)
        self.make('import time; time.sleep(10)', timeout_seconds=0.05)
        value = verify.run(self.spec, self.root / 'timeout')
        self.assertFalse(value['passed']); self.assertEqual(value['checks'][0]['status'], 'timeout')

    def test_changed_during_run_or_missing_input_do_not_pass(self):
        out = self.make('from pathlib import Path; Path("source.txt").write_text("changed")')
        self.assertFalse(verify.run(self.spec, out)['passed'])
        self.source.unlink()
        with self.assertRaises(ValueError):
            verify.run(self.spec, self.root / 'missing')

    def test_empty_checks_rejected(self):
        self.spec.write_text('{"goal":"empty", "checks":[]}')
        with self.assertRaises(ValueError):
            verify.run(self.spec, self.root / 'out')

    def test_spec_race_rejected_before_command_runs(self):
        out = self.make('from pathlib import Path; Path("ran").touch()')
        original = verify.capture
        def raced(paths):
            self.spec.write_text(self.spec.read_text() + '\n')
            return original(paths)
        with patch.object(verify, 'capture', side_effect=raced):
            with self.assertRaisesRegex(ValueError, 'Spec changed'):
                verify.run(self.spec, out)
        self.assertFalse((self.root / 'ran').exists())


if __name__ == '__main__':
    unittest.main()
