#!/usr/bin/env python3
"""Behavioral tests use only temporary vaults and local lock directories."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import agent_task as taskmod
from agent_task import Store, TaskError, hook_response
from install_claude_hooks import install

CLI = str(Path(__file__).resolve().parents[2] / 'bin/agent-task')
HOOK = str(Path(__file__).with_name('agent-task-claude.py'))


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agent-task-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.vault = self.base / 'vault'
        self.vault.mkdir()
        self.locks = self.base / 'locks'
        self.store = Store(self.vault, self.locks)
        self.env = {**os.environ, 'AGENT_TASK_VAULT': str(self.vault),
                    'AGENT_TASK_LOCK_DIR': str(self.locks)}
        self.env.pop('CLAUDE_ENV_FILE', None)

    def begin(self, task='implementation', agent='codex', session='one', **kwargs):
        return self.store.begin('environment', task, agent, session, 'Implement bounded component',
                                cwd=str(self.base), **kwargs)

    def run_cli(self, *args, expected=0):
        proc = subprocess.run([CLI, *args], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, expected, proc.stderr)
        return json.loads(proc.stdout) if proc.returncode == 0 else proc.stderr

    def test_concurrent_begin_has_one_owner(self):
        processes = [subprocess.Popen([CLI, 'begin', 'environment', 'same', '--agent', 'codex',
                                      '--session', 'session-%d' % i, '--scope', 'single owner'],
                                     env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for i in range(8)]
        results = [(process, process.communicate(timeout=15)) for process in processes]
        winners = [json.loads(output[0]) for process, output in results if process.returncode == 0]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.store.load('environment', 'same')['owner'], winners[0]['owner'])
        self.assertEqual(len(list((self.store.task_dir('environment', 'same') / 'events').glob('*.json'))), 1)

    def test_live_owner_rejects_conflicting_claim_and_mutation(self):
        self.begin()
        with self.assertRaisesRegex(TaskError, 'live owner'):
            self.store.claim('environment', 'implementation', 'claude', 'two', reclaim_stale=True)
        with self.assertRaisesRegex(TaskError, 'does not own'):
            self.store.change('environment', 'implementation', 'claude', 'two', 'heartbeat')

    def test_distinct_subtasks_allow_collaboration(self):
        a = self.begin('build')
        b = self.begin('review', agent='claude', session='two')
        self.assertEqual(len(self.store.all_tasks('environment')), 2)
        self.assertNotEqual(a['owner'], b['owner'])

    def test_stale_lease_requires_explicit_takeover(self):
        state = self.begin(ttl=60)
        later = taskmod.epoch(state['owner']['expires_at']) + 1
        with patch.object(taskmod.time, 'time', return_value=later):
            with self.assertRaisesRegex(TaskError, '--reclaim-stale'):
                self.store.claim('environment', 'implementation', 'claude', 'two')
            claimed = self.store.claim('environment', 'implementation', 'claude', 'two', reclaim_stale=True)
            self.assertEqual(claimed['owner']['session'], 'two')
            self.assertEqual(claimed['previous_owner']['session'], 'one')
            with self.assertRaises(TaskError):
                self.store.change('environment', 'implementation', 'codex', 'one', 'heartbeat')

    def test_stale_same_session_must_resume_before_update(self):
        state = self.begin(ttl=60)
        with patch.object(taskmod.time, 'time', return_value=taskmod.epoch(state['owner']['expires_at']) + 1):
            with self.assertRaisesRegex(TaskError, 'explicitly resume'):
                self.store.change('environment', 'implementation', 'codex', 'one', 'heartbeat')
            self.store.claim('environment', 'implementation', 'codex', 'one', action='resume')
            self.store.change('environment', 'implementation', 'codex', 'one', 'heartbeat')

    def test_close_requires_real_checkpoint_or_outcome(self):
        initial = self.begin()
        with self.assertRaises(TaskError):
            self.store.change('environment', 'implementation', 'codex', 'one', 'release', summary='Actual work')
        with self.assertRaises(TaskError):
            self.store.change('environment', 'implementation', 'codex', 'one', 'finish')
        self.assertEqual(self.store.load('environment', 'implementation')['revision'], initial['revision'])

    def test_release_then_claim_keeps_handoff(self):
        self.begin()
        self.store.change('environment', 'implementation', 'codex', 'one', 'release',
                          summary='Implemented parsing', next_step='Review error handling',
                          changes=['parser.py'], outputs=['/tmp/reviewable-output'], validation=['4 tests passed'])
        state = self.store.claim('environment', 'implementation', 'claude', 'two')
        self.assertEqual(state['checkpoint']['next'], 'Review error handling')
        self.assertEqual(state['owner']['session'], 'two')

    def test_event_commit_survives_interrupted_snapshot_refresh(self):
        initial = self.begin()
        original = taskmod.atomic_write
        def interrupt_snapshot(path, data):
            if Path(path).name == 'state.json':
                raise OSError('simulated interruption after committed event')
            original(path, data)
        with patch.object(taskmod, 'atomic_write', side_effect=interrupt_snapshot):
            with self.assertRaises(OSError):
                self.store.change('environment', 'implementation', 'codex', 'one', 'checkpoint',
                                  summary='Durably committed work', next_step='Continue safely')
        recovered = self.store.load('environment', 'implementation')
        self.assertEqual(recovered['revision'], initial['revision'] + 1)
        self.assertEqual(recovered['checkpoint']['summary'], 'Durably committed work')
        next_state = self.store.change('environment', 'implementation', 'codex', 'one', 'heartbeat')
        self.assertEqual(next_state['revision'], initial['revision'] + 2)
        stored = json.loads((self.store.task_dir('environment', 'implementation') / 'state.json').read_text())
        self.assertEqual(stored, next_state)

    def test_snapshot_readers_never_observe_partial_json(self):
        self.begin()
        path = self.store.task_dir('environment', 'implementation') / 'state.json'
        def update_many():
            for i in range(12):
                self.store.change('environment', 'implementation', 'codex', 'one', 'update', summary='Step %d' % i)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(update_many)
            reads = 0
            while not future.done():
                self.assertIsInstance(json.loads(path.read_text())['revision'], int)
                reads += 1
            future.result()
        self.assertGreater(reads, 0)

    def test_hook_never_claims_other_session(self):
        initial = self.begin(agent='claude')
        output = hook_response({'hook_event_name': 'SessionStart', 'session_id': 'other',
                                'cwd': str(self.base)}, self.vault, self.locks, env={})
        self.assertIn('implementation', output['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.store.load('environment', 'implementation'), initial)

    def test_hook_exact_session_logs_without_prompt_or_transcript(self):
        self.begin(agent='claude')
        env_file = self.base / 'claude-env'
        payload = {'hook_event_name': 'SessionStart', 'session_id': 'one', 'cwd': str(self.base),
                   'transcript_path': '/private/not-to-read', 'user_prompt': 'SENSITIVE_SENTINEL'}
        output = hook_response(payload, self.vault, self.locks, env={'CLAUDE_ENV_FILE': str(env_file)})
        state = self.store.load('environment', 'implementation')
        self.assertIn('SessionStart', state['lifecycle'])
        self.assertIsNone(state['checkpoint'])
        self.assertIn('AGENT_TASK_SESSION=one', env_file.read_text())
        self.assertNotIn('SENSITIVE_SENTINEL', json.dumps(state))
        self.assertNotIn('decision', output)

    def test_precompact_only_records_timestamp(self):
        self.begin(agent='claude')
        output = hook_response({'hook_event_name': 'PreCompact', 'session_id': 'one'},
                               self.vault, self.locks, env={})
        self.assertEqual(output, {})
        self.assertIn('PreCompact', self.store.load('environment', 'implementation')['lifecycle'])

    def test_stop_is_nonblocking_and_loop_guard_is_noop(self):
        self.begin(agent='claude')
        payload = {'hook_event_name': 'Stop', 'session_id': 'one'}
        output = hook_response(payload, self.vault, self.locks, env={})
        self.assertEqual(set(output), {'systemMessage'})
        state = self.store.load('environment', 'implementation')
        payload['stop_hook_active'] = True
        self.assertEqual(hook_response(payload, self.vault, self.locks, env={}), {})
        self.assertEqual(state, self.store.load('environment', 'implementation'))

    def test_session_end_expires_only_exact_matched_owner(self):
        self.begin(agent='claude')
        other = self.begin('other', agent='claude', session='other')
        hook_response({'hook_event_name': 'SessionEnd', 'session_id': 'one'},
                      self.vault, self.locks, env={})
        state = self.store.load('environment', 'implementation')
        self.assertFalse(self.store.live(state))
        self.assertEqual(state['status'], 'active')
        self.assertIsNone(state['checkpoint'])
        self.assertEqual(self.store.load('environment', 'other'), other)

    def test_stale_hook_does_not_renew_ownership(self):
        state = self.begin(agent='claude', ttl=60)
        expiry = state['owner']['expires_at']
        with patch.object(taskmod.time, 'time', return_value=taskmod.epoch(expiry) + 1):
            hook_response({'hook_event_name': 'Stop', 'session_id': 'one'}, self.vault, self.locks, env={})
            self.assertEqual(self.store.load('environment', 'implementation')['owner']['expires_at'], expiry)

    def test_malformed_hooks_fail_open(self):
        for raw in ['{broken', '[]', '{"hook_event_name":"Stop"}', 'x' * 70000,
                    '{"hook_event_name":"SessionStart","session_id":"../../bad"}']:
            process = subprocess.run([sys.executable, HOOK], input=raw, text=True,
                                     capture_output=True, env=self.env, timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(json.loads(process.stdout), {})
            self.assertEqual(process.stderr, '')
        self.assertFalse(self.store.root.exists())

    def test_hook_busy_lock_fails_open_without_mutation(self):
        initial = self.begin(agent='claude')
        with self.store.locked('environment', 'implementation'):
            started = time.monotonic()
            output = hook_response({'hook_event_name': 'Stop', 'session_id': 'one'},
                                   self.vault, self.locks, env={})
            self.assertLess(time.monotonic() - started, 1)
        self.assertIn('systemMessage', output)
        self.assertEqual(self.store.load('environment', 'implementation'), initial)

    def test_realistic_cli_handoff_lifecycle(self):
        self.run_cli('begin', 'environment', 'handoff', '--agent', 'codex', '--session', 'writer',
                     '--scope', 'Implement handoff helper', '--cwd', str(self.base))
        self.run_cli('checkpoint', 'environment', 'handoff', '--agent', 'codex', '--session', 'writer',
                     '--summary', 'Implemented helper', '--changes', 'agent_task.py',
                     '--output', str(self.base / 'report.txt'), '--validation', 'Ownership tests passed',
                     '--next', 'Independent review')
        self.run_cli('release', 'environment', 'handoff', '--agent', 'codex', '--session', 'writer',
                     '--summary', 'Implementation ready', '--next', 'Review lifecycle checks')
        self.run_cli('resume', 'environment', 'handoff', '--agent', 'claude', '--session', 'reviewer')
        result = self.run_cli('finish', 'environment', 'handoff', '--agent', 'claude', '--session', 'reviewer',
                              '--outcome', 'Implemented and reviewed handoff workflow',
                              '--validation', 'All focused tests passed')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['checkpoint']['next'], '')
        self.assertIn('Implemented and reviewed', Path(result['handoff_path']).read_text())
        self.assertEqual(self.run_cli('list'), [])
        self.assertEqual(len(self.run_cli('list', '--all')), 1)
        self.run_cli('claim', 'environment', 'handoff', '--agent', 'claude', '--session', 'reviewer', expected=1)

    def test_invalid_slug_cannot_escape_store(self):
        with self.assertRaises(TaskError):
            self.store.begin('../outside', 'task', 'codex', 'one', 'scope')
        self.assertFalse(self.store.root.exists())

    def test_hook_install_preserves_settings_and_is_idempotent(self):
        path = self.base / 'settings.json'
        original = {'permissions': {'allow': ['Read'], 'deny': ['Bash(forbidden *)']},
                    'unknownFutureSetting': {'keep': True},
                    'hooks': {'Stop': [{'matcher': '*', 'hooks': [
                        {'type': 'command', 'command': '/existing/hook', 'timeout': 12}]}],
                              'UserPromptSubmit': [{'hooks': [
                                  {'type': 'command', 'command': '/existing/prompt-hook'}]}]}}
        path.write_text(json.dumps(original))
        original_bytes = path.read_bytes()
        report = install(path, self.base / 'backups')
        self.assertEqual(Path(report['backup']).read_bytes(), original_bytes)
        modified = json.loads(path.read_text())
        self.assertEqual(modified['permissions'], original['permissions'])
        self.assertEqual(modified['unknownFutureSetting'], original['unknownFutureSetting'])
        self.assertEqual(modified['hooks']['Stop'][0], original['hooks']['Stop'][0])
        self.assertEqual(modified['hooks']['UserPromptSubmit'], original['hooks']['UserPromptSubmit'])
        first_bytes = path.read_bytes()
        self.assertEqual(install(path, self.base / 'backups')['changed'], [])
        self.assertEqual(path.read_bytes(), first_bytes)

    def test_hook_install_creates_missing_settings_in_temp_home(self):
        # Regression: a fresh HOME without ~/.claude/settings.json used to crash
        # with FileNotFoundError. Runs the real script with a temporary HOME only.
        home = self.base / 'home'
        home.mkdir()
        env = {**self.env, 'HOME': str(home)}
        script = str(Path(__file__).with_name('install_claude_hooks.py'))
        proc = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        settings = home / '.claude/settings.json'
        hooks = json.loads(settings.read_text())['hooks']
        self.assertEqual(sorted(hooks), sorted(taskmod.EVENTS))
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        again = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(json.loads(again.stdout)['changed'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
