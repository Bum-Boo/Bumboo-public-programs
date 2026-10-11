#!/usr/bin/env python3
"""Local advisory task ownership and explicit handoff checkpoints in a shared vault."""
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sys
import tempfile
import time

DEFAULT_VAULT = Path(os.environ.get('AGENT_TASK_VAULT', str(Path.home() / 'Documents/AgentVault')))
SLUG = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}\Z')
IDENTITY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,179}\Z')
EVENTS = {'SessionStart', 'PreCompact', 'Stop', 'SessionEnd'}


class TaskError(Exception):
    pass


def stamp(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else epoch,
                                  timezone.utc).isoformat(timespec='seconds')


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def validate_id(value, name='identity', slug=False):
    if not isinstance(value, str) or not (SLUG if slug else IDENTITY).fullmatch(value):
        raise TaskError('Invalid %s; use a short explicit %s' %
                        (name, 'lowercase project/task slug' if slug else 'agent/session identifier'))
    return value


def text_field(value, name, required=False):
    if value is None:
        if required:
            raise TaskError('%s is required' % name)
        return None
    if not isinstance(value, str) or len(value) > 8000 or '\x00' in value:
        raise TaskError('%s must be text of at most 8000 characters' % name)
    if required and not value.strip():
        raise TaskError('%s must not be empty' % name)
    return value.strip()


def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data.encode() if isinstance(data, str) else data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


class Store:
    def __init__(self, vault=None, lock_root=None):
        self.vault = Path(vault or os.environ.get('AGENT_TASK_VAULT') or DEFAULT_VAULT).expanduser().resolve()
        if not self.vault.is_dir():
            raise TaskError('Vault directory does not exist: %s' % self.vault)
        self.root = self.vault / '00_System/Agent Tasks'
        self.lock_root = Path(lock_root or os.environ.get('AGENT_TASK_LOCK_DIR') or
                              Path.home() / '.local/state/agent-task/locks')
        self.machine = socket.gethostname()

    def task_dir(self, project, task):
        validate_id(project, 'project', slug=True)
        validate_id(task, 'task', slug=True)
        path = self.root / project / task
        for parent in (self.vault / '00_System', self.root, path.parent, path):
            if parent.is_symlink():
                raise TaskError('Task directories must not be symlinks')
        return path

    @contextmanager
    def locked(self, project, task, timeout=5):
        path = self.task_dir(project, task)
        self.lock_root.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(str(path).encode()).hexdigest() + '.lock'
        with (self.lock_root / name).open('a') as handle:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TaskError('Task is busy; inspect/retry later')
                    time.sleep(min(0.025, timeout))
            try:
                yield path
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self, project, task):
        path = self.task_dir(project, task)
        snapshots = sorted((path / 'events').glob('[0-9]' * 8 + '.json'))
        if snapshots:
            # Each immutable event contains the committed state. state.json and
            # Handoff.md are atomic views; a crash while refreshing them is safe.
            event = json.loads(snapshots[-1].read_text())
            state = event['state']
            if event['revision'] != state['revision']:
                raise TaskError('Task event revision mismatch; manual inspection required')
        elif (path / 'state.json').exists():
            state = json.loads((path / 'state.json').read_text())
        else:
            raise TaskError('Task does not exist; begin it explicitly')
        if (state.get('schema') != 1 or state.get('project') != project or
                state.get('task') != task or not isinstance(state.get('revision'), int)):
            raise TaskError('Invalid task state; manual inspection required')
        return state

    def commit(self, state, action, actor=None):
        state = copy.deepcopy(state)
        state['revision'] += 1
        state['updated_at'] = stamp()
        path = self.task_dir(state['project'], state['task'])
        (path / 'events').mkdir(parents=True, exist_ok=True)
        event_path = path / 'events' / ('%08d.json' % state['revision'])
        if event_path.exists():
            raise TaskError('Event revision already exists; inspect before retrying')
        event = {'revision': state['revision'], 'at': state['updated_at'],
                 'action': action, 'actor': actor, 'state': state}
        atomic_write(event_path, json_text(event))
        atomic_write(path / 'state.json', json_text(state))
        atomic_write(path / 'Handoff.md', self.note(state))
        return state

    @staticmethod
    def owner_matches(owner, agent, session, machine):
        return bool(owner and owner['agent'] == agent and owner['session'] == session and
                    owner['machine'] == machine)

    @staticmethod
    def live(state):
        owner = state.get('owner')
        return bool(state['status'] == 'active' and owner and epoch(owner['expires_at']) > time.time())

    def actor(self, agent, session):
        return {'agent': validate_id(agent, 'agent'), 'session': validate_id(session, 'session'),
                'machine': self.machine}

    def renew(self, state, actor, ttl=None):
        duration = ttl if ttl is not None else (state.get('owner') or {}).get('ttl_seconds', 3600)
        if not isinstance(duration, int) or not 1 <= duration <= 86400:
            raise TaskError('TTL must be 1..86400 seconds')
        now = time.time()
        old = state.get('owner')
        same = self.owner_matches(old, actor['agent'], actor['session'], actor['machine'])
        state['owner'] = {**actor, 'claimed_at': old['claimed_at'] if same else stamp(now),
                          'heartbeat_at': stamp(now), 'expires_at': stamp(now + duration),
                          'ttl_seconds': duration}

    def require_owner(self, state, actor):
        if not self.owner_matches(state.get('owner'), actor['agent'], actor['session'], actor['machine']):
            raise TaskError('This session does not own the task; show it and explicitly claim/resume')
        if not self.live(state):
            raise TaskError('Lease expired or task closed; explicitly resume before changing it')

    def begin(self, project, task, agent, session, scope, title=None, cwd=None, ttl=3600):
        actor = self.actor(agent, session)
        scope = text_field(scope, 'scope', required=True)
        title = text_field(title or task, 'title', required=True)
        cwd = str(Path(cwd or os.getcwd()).expanduser().resolve())
        with self.locked(project, task):
            path = self.task_dir(project, task)
            if path.exists() and any(path.iterdir()):
                raise TaskError('Task already exists; show it and use claim/resume instead')
            state = {'schema': 1, 'project': project, 'task': task, 'title': title,
                     'scope': scope, 'cwd': cwd, 'status': 'active', 'revision': 0,
                     'created_at': stamp(), 'updated_at': stamp(), 'owner': None,
                     'checkpoint': None, 'lifecycle': {}, 'outcome': None}
            self.renew(state, actor, ttl)
            return self.commit(state, 'begin', actor)

    def claim(self, project, task, agent, session, reclaim_stale=False, ttl=None, action='claim'):
        actor = self.actor(agent, session)
        with self.locked(project, task):
            state = self.load(project, task)
            if state['status'] == 'completed':
                raise TaskError('Task is completed; create a distinct follow-up task')
            owner = state.get('owner')
            same = self.owner_matches(owner, agent, session, self.machine)
            if self.live(state) and not same:
                raise TaskError('Task has a live owner (%s / %s); use a separate scoped subtask' %
                                (owner['agent'], owner['session']))
            if owner and not self.live(state) and not same and not reclaim_stale:
                raise TaskError('Previous lease is stale; inspect the handoff and use --reclaim-stale explicitly')
            if owner and not same:
                state['previous_owner'] = owner
            state['status'] = 'active'
            self.renew(state, actor, ttl)
            return self.commit(state, action, actor)

    def change(self, project, task, agent, session, action, summary=None, next_step=None,
               changes=None, outputs=None, validation=None, blocked=None, outcome=None):
        actor = self.actor(agent, session)
        if action not in {'heartbeat', 'update', 'checkpoint', 'release', 'finish'}:
            raise TaskError('Unknown task action')
        summary = text_field(summary, 'summary', required=action in {'checkpoint', 'release'})
        next_step = text_field(next_step, 'next', required=action in {'checkpoint', 'release'})
        outcome = text_field(outcome, 'outcome', required=action == 'finish')
        blocked = text_field(blocked, 'blocked')
        supplied = any(x is not None for x in (summary, next_step, changes, outputs, validation, blocked))
        if action == 'update' and not supplied:
            raise TaskError('update needs a summary, next step, changes, output, validation, or blocker')
        for values, field in ((changes, 'changes'), (outputs, 'output'), (validation, 'validation')):
            if values is not None:
                if len(values) > 50:
                    raise TaskError('Too many %s entries' % field)
                for item in values:
                    text_field(item, field, required=True)
        with self.locked(project, task):
            state = self.load(project, task)
            self.require_owner(state, actor)
            self.renew(state, actor)
            if action != 'heartbeat':
                checkpoint = copy.deepcopy(state.get('checkpoint') or
                                           {'summary': '', 'next': '', 'changes': [], 'outputs': [],
                                            'validation': [], 'blocked': ''})
                for key, value in [('summary', summary), ('next', next_step), ('changes', changes),
                                   ('outputs', outputs), ('validation', validation), ('blocked', blocked)]:
                    if value is not None:
                        checkpoint[key] = value
                if action == 'finish':
                    checkpoint['summary'] = summary or outcome
                    checkpoint['next'] = ''
                checkpoint.update({'at': stamp(), 'by': actor, 'complete': action != 'update'})
                state['checkpoint'] = checkpoint
            if action in {'release', 'finish'}:
                state['previous_owner'] = state['owner']
                state['owner'] = None
                state['status'] = 'completed' if action == 'finish' else 'released'
                state['closed_at'] = stamp()
            if action == 'finish':
                state['outcome'] = outcome
            return self.commit(state, action, actor)

    def all_tasks(self, project=None):
        if project:
            validate_id(project, 'project', slug=True)
            directories = sorted((self.root / project).glob('*'))
        else:
            directories = sorted(self.root.glob('*/*'))
        tasks = []
        for path in directories:
            if not path.is_dir() or path.is_symlink() or not SLUG.fullmatch(path.name):
                continue
            try:
                tasks.append(self.load(path.parent.name, path.name))
            except (TaskError, OSError, ValueError, KeyError):
                continue
        return tasks

    @staticmethod
    def relevant(state, cwd):
        if not cwd:
            return False
        try:
            here = Path(cwd).resolve()
            task_path = Path(state['cwd']).resolve()
            return here == task_path or task_path in here.parents
        except (KeyError, OSError, ValueError):
            return False

    def view(self, state):
        result = copy.deepcopy(state)
        result['lease'] = 'live' if self.live(state) else 'stale' if state.get('owner') else 'unowned'
        result['handoff_path'] = str(self.task_dir(state['project'], state['task']) / 'Handoff.md')
        return result

    def note(self, state):
        owner = state.get('owner')
        lines = ['# ' + state['title'], '',
                 'Generated by `agent-task`; use the CLI to update this record.', '',
                 '- Project/task: `%s/%s`' % (state['project'], state['task']),
                 '- Status: ' + state['status'], '- Revision: ' + str(state['revision']),
                 '- Scope: ' + state['scope'],
                 '- Working directory: `' + state['cwd'] + '`',
                 '- Updated: ' + state['updated_at']]
        if owner:
            lines += ['- Owner: `%s` / session `%s` / machine `%s`' %
                      (owner['agent'], owner['session'], owner['machine']),
                      '- Lease expires: ' + owner['expires_at']]
        checkpoint = state.get('checkpoint')
        if checkpoint:
            lines += ['', '## Checkpoint', '', checkpoint['summary'], '',
                      '- Recorded: ' + checkpoint['at']]
            for field, title in [('changes', 'Changes'), ('outputs', 'Outputs'), ('validation', 'Validation')]:
                if checkpoint.get(field):
                    lines += ['', '## ' + title, ''] + ['- ' + item for item in checkpoint[field]]
            if checkpoint.get('blocked'):
                lines += ['', '## Blocked', '', checkpoint['blocked']]
            if checkpoint.get('next'):
                lines += ['', '## Next', '', checkpoint['next']]
        else:
            lines += ['', 'No explicit checkpoint recorded yet. Lifecycle hooks do not invent one.']
        if state.get('outcome'):
            lines += ['', '## Completed outcome', '', state['outcome']]
        lines += ['', 'Ownership is advisory for local agents. Syncthing is not a distributed lock.', '']
        return '\n'.join(lines)

    def lifecycle(self, project, task, session, event):
        if event not in EVENTS:
            return None
        with self.locked(project, task, timeout=0.1):
            state = self.load(project, task)
            if state['status'] != 'active' or not self.owner_matches(state.get('owner'), 'claude', session, self.machine):
                return None
            at = stamp()
            # Hook invocations only record observed lifecycle timestamps. They do
            # not claim tasks, invent work summaries, or silently complete work.
            if state['lifecycle'].get(event) == at:
                return state
            state['lifecycle'][event] = at
            if event == 'SessionEnd':
                state['owner']['expires_at'] = at
            elif self.live(state):
                self.renew(state, self.actor('claude', session))
            return self.commit(state, 'hook:' + event, self.actor('claude', session))


def hook_response(payload, vault=None, lock_root=None, env=None):
    """Never read transcripts, raw prompts, tool input, or another owner's task."""
    env = os.environ if env is None else env
    if not isinstance(payload, dict):
        return {}
    event, session = payload.get('hook_event_name'), payload.get('session_id')
    if event not in EVENTS or not isinstance(session, str) or not IDENTITY.fullmatch(session):
        return {}
    if event == 'Stop' and payload.get('stop_hook_active'):
        return {}
    store = Store(vault, lock_root)
    if event == 'SessionStart' and env.get('CLAUDE_ENV_FILE'):
        # Supported Claude mechanism; this exports a pointer, never task contents.
        with open(env['CLAUDE_ENV_FILE'], 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write('\nexport AGENT_TASK_SESSION=%s\nexport AGENT_TASK_AGENT=claude\n' % shlex.quote(session))
            handle.flush()
            fcntl.flock(handle, fcntl.LOCK_UN)
    tasks = store.all_tasks()
    tracked = [state for state in tasks if state['status'] == 'active' and
               store.owner_matches(state.get('owner'), 'claude', session, store.machine)]
    for state in tracked:
        try:
            store.lifecycle(state['project'], state['task'], session, event)
        except (TaskError, OSError, ValueError, KeyError):
            pass
    if event in {'SessionEnd', 'PreCompact'}:
        return {}
    relevant = tracked or [state for state in tasks if state['status'] != 'completed' and
                          store.relevant(state, payload.get('cwd'))]
    lines = []
    for state in relevant[:5]:
        owner = state.get('owner')
        who = (owner['agent'] + '/' + owner['session']) if owner else 'unowned'
        lines.append('%s/%s: %s; owner %s; read %s' %
                     (state['project'], state['task'], state['status'], who,
                      store.task_dir(state['project'], state['task']) / 'Handoff.md'))
        if state.get('checkpoint') and state['checkpoint'].get('next'):
            lines.append('Next: ' + state['checkpoint']['next'][:600])
    if event == 'SessionStart':
        lines.insert(0, 'Agent handoff session: %s. Use agent-task only for meaningful multi-step work.' % session)
        lines.append('Read your configured shared task handoff instructions when tracking work. '
                     'Inspect the explicit task before claim/resume; never take another live owner\'s scope.')
        return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': '\n'.join(lines)}}
    if not tracked:
        return {}
    lines.append('Checkpoint reminder: record actual changes, output, validation, and next step with '
                 'agent-task checkpoint; finish with a verified outcome or release with a handoff. '
                 'This reminder does not block stopping or fabricate a summary.')
    return {'systemMessage': '\n'.join(lines)}


def hook_main():
    try:
        raw = sys.stdin.read(65537)
        output = hook_response(json.loads(raw)) if len(raw) <= 65536 else {}
    except Exception:
        output = {}
    print(json.dumps(output, ensure_ascii=False))
    return 0


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--vault', help='Vault root; default is the shared Obsidian vault')
    commands = result.add_subparsers(dest='action', required=True)
    p = commands.add_parser('list', help='List task records only; no full-vault scan')
    p.add_argument('--project')
    p.add_argument('--cwd', help='Only tasks relevant to this working directory')
    p.add_argument('--all', action='store_true', help='Include completed tasks')
    for action in ('show', 'begin', 'claim', 'resume', 'heartbeat', 'update', 'checkpoint', 'release', 'finish'):
        p = commands.add_parser(action)
        p.add_argument('project')
        p.add_argument('task', help='Explicit task/subtask slug; scopes may run alongside each other')
        if action == 'show':
            continue
        p.add_argument('--agent', default=os.environ.get('AGENT_TASK_AGENT'))
        p.add_argument('--session', default=os.environ.get('AGENT_TASK_SESSION') or os.environ.get('CODEX_THREAD_ID'))
        if action == 'begin':
            p.add_argument('--scope', required=True)
            p.add_argument('--title')
            p.add_argument('--cwd')
            p.add_argument('--ttl', type=int, default=3600, help='Lease seconds, default 3600; refresh during long work')
        if action in ('claim', 'resume'):
            p.add_argument('--reclaim-stale', action='store_true')
            p.add_argument('--ttl', type=int)
        if action in ('update', 'checkpoint', 'release', 'finish'):
            p.add_argument('--summary')
            p.add_argument('--next', dest='next_step')
            p.add_argument('--changes', action='append')
            p.add_argument('--output', dest='outputs', action='append')
            p.add_argument('--validation', action='append')
            p.add_argument('--blocked')
            if action == 'finish':
                p.add_argument('--outcome', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = Store(args.vault)
        if args.action == 'list':
            states = [state for state in store.all_tasks(args.project)
                      if (args.all or state['status'] != 'completed') and
                      (not args.cwd or store.relevant(state, args.cwd))]
            output = [store.view(state) for state in states]
        elif args.action == 'show':
            output = store.view(store.load(args.project, args.task))
        else:
            if not args.agent or not args.session:
                raise TaskError('Set --agent and --session explicitly (or AGENT_TASK_AGENT/AGENT_TASK_SESSION)')
            base = (args.project, args.task, args.agent, args.session)
            if args.action == 'begin':
                state = store.begin(*base, scope=args.scope, title=args.title, cwd=args.cwd, ttl=args.ttl)
            elif args.action in ('claim', 'resume'):
                state = store.claim(*base, reclaim_stale=args.reclaim_stale, ttl=args.ttl, action=args.action)
            else:
                fields = {name: getattr(args, name, None) for name in
                          ('summary', 'next_step', 'changes', 'outputs', 'validation', 'blocked', 'outcome')}
                state = store.change(*base, action=args.action, **fields)
            output = store.view(state)
        print(json_text(output), end='')
        return 0
    except (TaskError, OSError, ValueError, KeyError) as error:
        print('agent-task: %s' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
