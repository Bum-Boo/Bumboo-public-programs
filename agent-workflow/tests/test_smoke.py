"""End-to-end smoke tests through the documented bin/ wrappers.

Hermetic: temporary HOME, a copy of the synthetic examples/vault, and stub
`codex`/`claude` executables on PATH. No real model CLI, remote host, network,
systemd unit or user settings are touched.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin'

STUB_CLAUDE = '''#!/bin/sh
cat >/dev/null
if [ "$1" = auth ]; then
  echo '{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "firstParty"}'
  exit 0
fi
echo '{"is_error": false, "result": "synthetic", "structured_output": {"verdict": "approve", "summary": "synthetic approval", "findings": []}}'
'''

STUB_CODEX = '''#!/bin/sh
cat >/dev/null
if [ "$1" = login ]; then
  echo 'Logged in using ChatGPT'
  exit 0
fi
out=
while [ $# -gt 0 ]; do
  if [ "$1" = -o ]; then out=$2; fi
  shift
done
echo 'synthetic codex analysis' > "$out"
'''


class SmokeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='agent-workflow-smoke-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.vault = self.base / 'vault'
        shutil.copytree(ROOT / 'examples/vault', self.vault)
        self.stubs = self.base / 'stubs'
        self.stubs.mkdir()
        for name, body in (('claude', STUB_CLAUDE), ('codex', STUB_CODEX)):
            path = self.stubs / name
            path.write_text(body)
            path.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items()
                    if key not in ('AGENT_TASK_SESSION', 'AGENT_TASK_AGENT', 'CODEX_THREAD_ID', 'CLAUDE_ENV_FILE')}
        self.env.update(HOME=str(self.home), AGENT_WORKFLOW_PYTHON=sys.executable,
                        AGENT_TASK_VAULT=str(self.vault),
                        PATH=os.pathsep.join([str(self.stubs), str(BIN), os.environ.get('PATH', '')]))

    def cli(self, *argv, expected=0, executable=None):
        proc = subprocess.run([str(executable or BIN / argv[0]), *argv[1:]], env=self.env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return proc.stdout

    def test_context_preview_refresh_check_resume(self):
        preview = self.cli('agent-context', '--vault', str(self.vault), 'preview')
        self.assertIn('## Sample', preview)
        self.assertIn('Verify a local result', preview)
        # check needs a generated board first.
        self.cli('agent-context', '--vault', str(self.vault), 'check', expected=2)
        self.assertTrue(json.loads(self.cli('agent-context', '--vault', str(self.vault), 'refresh'))['changed'])
        self.assertEqual((self.vault / '00_System/Now.md').read_text(), preview)
        self.assertTrue(json.loads(self.cli('agent-context', '--vault', str(self.vault), 'check'))['ok'])
        self.assertEqual(json.loads(self.cli('agent-context', '--vault', str(self.vault), 'resume', 'demo'))[0]['project'], 'Sample')
        self.cli('agent-context', '--vault', str(self.vault), 'resume', 'no-such-alias', expected=1)

    def test_task_lifecycle(self):
        self.assertEqual(json.loads(self.cli('agent-task', '--vault', str(self.vault), 'list')), [])
        ident = ['--agent', 'codex', '--session', 'smoke']
        self.cli('agent-task', 'begin', 'sample', 'smoke', *ident, '--scope', 'Synthetic smoke', '--cwd', str(self.base))
        self.cli('agent-task', 'checkpoint', 'sample', 'smoke', *ident, '--summary', 'Did a thing', '--next', 'Review')
        self.cli('agent-task', 'claim', 'sample', 'smoke', '--agent', 'claude', '--session', 'other', expected=1)
        done = json.loads(self.cli('agent-task', 'finish', 'sample', 'smoke', *ident, '--outcome', 'Verified'))
        self.assertEqual(done['status'], 'completed')
        self.assertIn('Verified', Path(done['handoff_path']).read_text())
        self.assertEqual(len(json.loads(self.cli('agent-task', 'list', '--all'))), 1)

    def test_offline_spec_and_verify_receipt(self):
        spec = self.base / 'offline.json'
        spec.write_text(subprocess.run([sys.executable, str(ROOT / 'examples/make-offline-spec.py')],
                                       capture_output=True, text=True, check=True).stdout)
        out = self.base / 'receipt'
        self.assertTrue(json.loads(self.cli('agent-verify', 'run', str(spec), '--out', str(out)))['passed'])
        self.assertTrue(json.loads(self.cli('agent-verify', 'check', str(out / 'result.json')))['evidence_current'])
        # An existing receipt directory is never reused.
        self.cli('agent-verify', 'run', str(spec), '--out', str(out), expected=2)

    def test_orchestrate_review_and_research_with_stub_clis(self):
        source = self.base / 'project'
        source.mkdir()
        (source / 'app.py').write_text('print("synthetic")\n')
        common = ['--root', str(self.base / 'queue'), '--config', str(self.base / 'config.json')]
        ids = []
        for kind in ('review', 'research'):
            spec = self.base / f'{kind}.json'
            spec.write_text(json.dumps({'title': f'smoke {kind}', 'kind': kind, 'source': str(source),
                                        'prompt': 'Review app.py for synthetic smoke coverage.'}))
            ids.append(json.loads(self.cli('agent-orchestrate', *common, 'submit', str(spec)))['id'])
        results = {r['id']: r for r in json.loads(self.cli('agent-orchestrate', *common, 'worker'))}
        self.assertEqual({results[i]['status'] for i in ids}, {'ready'}, results)
        self.assertEqual(results[ids[0]]['review']['verdict'], 'approve')
        status = json.loads(self.cli('agent-orchestrate', *common, 'status'))
        self.assertEqual(sorted(j['status'] for j in status), ['ready', 'ready'])
        self.assertIn('synthetic approval', (self.base / 'queue/latest.md').read_text())
        self.cli('agent-orchestrate', *common, 'cancel', ids[0], expected=1)

    def test_wrappers_work_through_symlink_install(self):
        # Regression: systemd units call %h/.local/bin/agent-orchestrate; a symlinked
        # wrapper used to resolve TASK_ROOT to ~/.local and fail to find the script.
        local_bin = self.home / '.local/bin'
        local_bin.mkdir(parents=True)
        for name in ('agent-context', 'agent-task', 'agent-verify', 'agent-orchestrate'):
            (local_bin / name).symlink_to(BIN / name)
        self.assertIn('## Sample', self.cli('agent-context', '--vault', str(self.vault), 'preview',
                                            executable=local_bin / 'agent-context'))
        self.assertEqual(json.loads(self.cli('agent-task', 'list', executable=local_bin / 'agent-task')), [])
        self.assertEqual(json.loads(self.cli('agent-orchestrate', '--root', str(self.base / 'q'), 'status',
                                             executable=local_bin / 'agent-orchestrate')), [])
        self.cli('agent-verify', '--help', executable=local_bin / 'agent-verify')


if __name__ == '__main__':
    unittest.main()
