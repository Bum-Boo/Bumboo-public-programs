import contextlib
import io
import json
from pathlib import Path
import tempfile
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import orchestrate as o


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'README.md').write_text('before\n')
        self.config = self.base / 'config.json'
        o.write(self.config, {'max_jobs_per_day': 4, 'watches': [
            {'name': 'docs', 'type': 'docs', 'source': str(self.source),
             'patterns': ['*.md'], 'prompt': 'Update guide.'}]})
        self.queue = o.Queue(self.base / 'queue', self.config)

    def submit(self, **extra):
        spec = dict(kind='pipeline', source=str(self.source), prompt='Implement feature.', **extra)
        return self.queue.submit(spec)

    def test_frozen_input_and_exclusions(self):
        (self.source / '.env').write_text('synthetic secret')
        (self.source / 'link').symlink_to(self.source / 'README.md')
        job = self.submit()
        (self.source / 'README.md').write_text('after')
        input_path = self.queue.path(job) / 'input'
        self.assertEqual((input_path / 'README.md').read_text(), 'before\n')
        self.assertFalse((input_path / '.env').exists())
        self.assertFalse((input_path / 'link').exists())

    def test_event_baseline_change_and_deduplication(self):
        self.assertEqual(self.queue.watch(), [])
        (self.source / 'README.md').write_text('after')
        jobs = self.queue.watch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(self.queue.watch(), [])
        saved = self.queue.load(jobs[0])
        self.assertEqual(saved['spec']['schedule'], 'night')
        duplicate = self.queue.submit(saved['spec'], saved['event'])
        self.assertEqual(duplicate['id'], saved['id'])
        self.assertEqual(len(self.queue.jobs()), 1)

    def test_interrupted_worker_blocks_without_repeat(self):
        job = self.submit()
        job.update(status='running', remote_jobs=[{'job': 'existing', 'host': 'himmel'}])
        self.queue.save(job)
        with patch.object(self.queue, 'execute') as execute:
            self.assertEqual(self.queue.worker(), [])
            execute.assert_not_called()
        recovered = self.queue.load(job['id'])
        self.assertEqual(recovered['status'], 'blocked')
        self.assertEqual(recovered['remote_jobs'][0]['job'], 'existing')

    def test_night_gate_and_daily_cap(self):
        self.queue.config['max_jobs_per_day'] = 1
        job = self.submit(schedule='night')
        self.assertEqual(self.queue.worker(), [])
        def execute(item):
            item['status'] = 'ready'
            self.queue.save(item)
            return item
        with patch.object(self.queue, 'execute', side_effect=execute):
            self.assertEqual(len(self.queue.worker(night=True)), 1)
            second = self.submit()
            self.assertEqual(self.queue.worker(), [])
            self.assertEqual(self.queue.load(second['id'])['status'], 'queued')

    def test_review_rejection_and_missing_verdict(self):
        for verdict, expected in [('changes_required', 'needs_changes'), (None, 'blocked')]:
            job = self.submit()
            def model(item, provider, *args, **kwargs):
                if provider == 'codex':
                    (self.queue.path(item) / 'work' / 'feature.py').write_text('value = 1\n')
                    return 'done'
                return {'structured_output': {'verdict': verdict, 'summary': 'review', 'findings': []}}
            with patch.object(self.queue, 'model', side_effect=model):
                result = self.queue.execute(job)
            self.assertEqual(result['status'], expected)
            self.assertFalse((self.source / 'feature.py').exists())

    def test_reviewer_mutation_blocks(self):
        job = self.submit()
        def model(item, provider, *args, **kwargs):
            if provider == 'claude':
                (self.queue.path(item) / 'work' / 'README.md').write_text('mutated')
                return {'structured_output': {'verdict': 'approve'}}
        with patch.object(self.queue, 'model', side_effect=model):
            result = self.queue.execute(job)
        self.assertEqual(result['status'], 'blocked')

    def test_remote_resources_held_blocks_without_fetch(self):
        job = self.submit(checks=[['python3', 'test.py']])
        (self.queue.path(job) / 'work').mkdir()
        def run(argv, *args, **kwargs):
            if 'run' in argv:
                return json.dumps({'job': 'remote-existing', 'remote': {'ok': True}})
            if 'info' in argv:
                return json.dumps({'status': 'completed', 'exit_code': 0, 'resources_held': True})
            self.fail('Must not fetch held resources')
        with patch.object(o, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'resources'):
                self.queue.remote_checks(job)
        self.assertEqual(job['remote_jobs'][0]['job'], 'remote-existing')

    def test_submission_unknown_retains_prepared_id(self):
        job = self.submit(checks=[['python3', 'test.py']])
        def run(argv, cwd, output, *args, **kwargs):
            output.with_suffix('.stderr').write_text('Prepared himmel / 20261010-abc; inspect before retrying')
            raise RuntimeError('SSH lost')
        with patch.object(o, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'SSH'):
                self.queue.remote_checks(job)
        self.assertTrue(job['remote_jobs'][0]['uncertain'])
        self.assertEqual(job['remote_jobs'][0]['job'], '20261010-abc')

    def test_paid_api_auth_rejected(self):
        folder = self.base / 'auth'
        folder.mkdir()
        with patch.object(o, 'run', return_value=json.dumps({'loggedIn': True, 'authMethod': 'api_key'})):
            with self.assertRaisesRegex(RuntimeError, 'subscription'):
                self.queue.auth('claude', folder)

    def test_file_modes_are_part_of_manifest(self):
        path = self.source / 'README.md'
        before = o.manifest(self.source)
        path.chmod(0o755)
        self.assertNotEqual(o.manifest(self.source), before)

    def test_descendant_ignoring_term_is_killed(self):
        child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(90)"
        parent = ('import subprocess,sys,time,pathlib; '
                  'p=subprocess.Popen([sys.executable,"-c",sys.argv[1]]); '
                  'pathlib.Path("child.pid").write_text(str(p.pid)); time.sleep(90)')
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                o.run([sys.executable, '-c', parent, child], self.source, self.base / 'timeout.log', timeout=5)
            pid = int((self.source / 'child.pid').read_text())
            stat = Path(f'/proc/{pid}/stat')
            if stat.exists():
                self.assertEqual(stat.read_text().rsplit(')', 1)[1].split()[0], 'Z')
        finally:
            p = self.source / 'child.pid'
            if p.exists():
                try:
                    os.kill(int(p.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_crash_recovers_job_id_from_submission_log(self):
        job = self.submit()
        job['status'] = 'running'
        self.queue.save(job)
        (self.queue.path(job) / 'remote-submit-0.stderr').write_text('Prepared himmel / known-remote-job')
        self.queue.worker()
        state = self.queue.load(job['id'])
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['remote_jobs'][0]['job'], 'known-remote-job')

    def test_event_snapshot_race_is_deferred(self):
        expected = o.manifest(self.source)
        (self.source / 'README.md').write_text('changed while watching')
        with self.assertRaisesRegex(RuntimeError, 'changed during'):
            self.queue.submit({'source': str(self.source), 'prompt': 'Update docs'},
                              'event-old', expected, ['*.md'])
        self.assertEqual(self.queue.jobs(), [])

    def test_night_release_survives_busy_worker(self):
        job = self.submit(schedule='night')
        with o.lock(self.queue.root / 'worker.lock'):
            self.assertEqual(self.queue.worker(night=True), [])
        self.assertIn('night_released', self.queue.load(job['id']))
        with patch.object(self.queue, 'execute', side_effect=lambda j: j):
            self.assertEqual(len(self.queue.worker()), 1)

    def test_live_previous_group_blocks_new_work(self):
        job = self.submit()
        job['status'] = 'running'
        self.queue.save(job)
        o.write(self.queue.path(job) / 'writer.process.json', {'pgid': os.getpgrp(), 'status': 'running'})
        self.submit()
        with patch.object(self.queue, 'execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'still active'):
                self.queue.worker()
            execute.assert_not_called()

    def test_pr_event_uses_pinned_refs_and_deduplicates(self):
        self.queue.config['watches'] = [{'name': 'pr', 'type': 'github-pr', 'repo': 'example/repo'}]
        head = ['a' * 40]
        calls = []
        def run(argv, cwd, output, *args, **kwargs):
            calls.append(argv)
            if argv[:3] == ['gh', 'pr', 'list']:
                return json.dumps([{'number': 1, 'headRefOid': head[0], 'baseRefOid': 'b' * 40, 'title': 'PR'}])
            if argv[:2] == ['gh', 'api']:
                output.write_text('synthetic pinned diff')
                return 'synthetic pinned diff'
            self.fail(str(argv))
        with patch.object(o, 'run', side_effect=run):
            self.assertEqual(self.queue.watch(), [])
            head[0] = 'c' * 40
            job_ids = self.queue.watch()
            self.assertEqual(len(job_ids), 1)
            self.assertEqual(self.queue.watch(), [])
        compare = next(argv for argv in calls if argv[:2] == ['gh', 'api'])
        self.assertEqual(compare[2], 'repos/example/repo/compare/' + 'b' * 40 + '...' + 'c' * 40)
        job = self.queue.load(job_ids[0])
        self.assertEqual(job['spec']['kind'], 'research')
        self.assertEqual((self.queue.path(job) / 'input/changes.diff').read_text(), 'synthetic pinned diff')

    def test_claude_error_and_denials_block(self):
        job = self.submit()
        (self.queue.path(job) / 'work').mkdir()
        for result in [{'is_error': True}, {'is_error': False, 'permission_denials': [{'tool_name': 'Read'}]}]:
            with patch.object(self.queue, 'auth'), patch.object(o, 'run', return_value=json.dumps(result)):
                with self.assertRaisesRegex(RuntimeError, 'error or denied'):
                    self.queue.model(job, 'claude', 'Review only', label='review')

    def test_review_only_does_not_call_writer(self):
        job = self.queue.submit({'kind': 'review', 'source': str(self.source), 'prompt': 'Review this.'})
        result_json = {'structured_output': {'verdict': 'approve', 'summary': 'Reviewed', 'findings': []}}
        with patch.object(self.queue, 'model', return_value=result_json) as model:
            result = self.queue.execute(job)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.args[1], 'claude')


if __name__ == '__main__':
    unittest.main()
