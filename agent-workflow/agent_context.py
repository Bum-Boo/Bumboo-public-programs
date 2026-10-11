#!/usr/bin/env python3
"""Small derived Now board; project notes remain the only state store."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import yaml

DEFAULT_VAULT = Path(os.environ.get('AGENT_TASK_VAULT', str(Path.home() / 'Documents/AgentVault')))
MARKER = '<!-- agent-context sha256:'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clip(value, length):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text if len(text) <= length else text[:max(0, length - 1)] + '…'


def projects(vault):
    records = []
    for path in sorted((vault / '30_Projects').glob('*/00 현재 상태.md')):
        data = path.read_bytes()
        text = data.decode('utf-8-sig').replace('\r\n', '\n')
        if text.startswith('---\n'):
            pieces = text.split('---\n', 2)
            if len(pieces) != 3:
                raise ValueError(f'Unclosed frontmatter: {path}')
            meta = yaml.safe_load(pieces[1])
            if not isinstance(meta, dict):
                raise ValueError(f'Invalid frontmatter: {path}')
            required = ['project', 'status', 'done', 'summary', 'next', 'updated', 'agent']
            missing = [key for key in required if key not in meta]
            if missing or not isinstance(meta.get('done'), bool):
                raise ValueError(f'Invalid project metadata {path}: missing={missing}, done must be boolean')
            aliases = meta.get('aliases', [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
                raise ValueError(f'aliases must be a string list: {path}')
            if meta['status'] not in ['active', 'waiting', 'review', 'ongoing', 'done', 'archived']:
                raise ValueError(f'Unknown status: {path}')
            meta['legacy'] = False
        else:
            # Other live owners may still have prose-only states. Keep them visible.
            def field(name):
                match = re.search(r'^- ' + name + r':\s*(.+)', text, re.M)
                return match.group(1) if match else ''
            date = re.search(r'갱신:\s*(\d{4}-\d{2}-\d{2})\s*(\S+)', text)
            aliases = []
            registry = vault / '30_Projects/Index.md'
            if registry.is_file():
                for line in registry.read_text().splitlines():
                    cells = line.split('|')
                    if len(cells) > 4 and path.parent.name in cells[2]:
                        aliases.extend(a.strip() for a in cells[3].split(',') if a.strip())
            meta = dict(project=path.parent.name, status='active', done=False,
                        summary=field('현재'), next=field('다음') or field('후속') or '현재 상태의 정본·인계 확인',
                        updated=date[1] if date else '미상', agent=date[2] if date else '미상',
                        aliases=aliases, legacy=True)
        records.append(dict(meta, path=path.relative_to(vault).as_posix(),
                            short=path.parent.name, sha256=sha(data)))
    if not records:
        raise ValueError('No project states found; refusing an empty board')
    return records


def fingerprint(records):
    return sha(json.dumps([(r['path'], r['sha256']) for r in records]).encode())


def render(records, limit=4096):
    # done is set only by the user. A review/done status alone cannot hide work.
    active = [r for r in records if not r['done']]
    prefix = ('# Now — 진행 중 작업\n\n'
              '> 자동 생성. 상태 정본을 고친 뒤 `agent-context refresh`. 전체 별칭·완료 작업은 '
              '[[../30_Projects/Index|레지스트리]] 또는 `agent-context resume "별칭"`.\n\n')
    for width in range(56, 3, -1):
        sections = []
        for r in active:
            alias = clip(' · '.join(r.get('aliases', [])[:2]) or r['short'], max(8, width // 2))
            stamp = str(r['updated'])[5:] if re.match(r'\d{4}-', str(r['updated'])) else str(r['updated'])
            text = (f"## {r['short']}\n- 별칭: {alias}\n"
                    f"- 이어가기: [[../{r['path'][:-3]}|현재 상태]]\n"
                    f"- 다음: {clip(r['next'], width)} ({stamp} {r['agent']})\n")
            sections.append(text)
        body = prefix + '\n'.join(sections)
        result = MARKER + sha(body.encode()) + ' -->\n' + body
        if len(result.encode()) <= limit:
            return result
    raise ValueError(f'All {len(active)} active projects cannot fit in {limit} bytes; no project was dropped')


def managed(text):
    first, sep, body = text.partition('\n')
    return bool(sep and first == MARKER + sha(body.encode()) + ' -->')


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def refresh(vault, limit, adopt_sha=None):
    path = vault / '00_System/Now.md'
    lock = Path.home() / '.local/state/agent-workflow/context.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        before = path.read_bytes() if path.exists() else b''
        if before and not managed(before.decode()):
            if not adopt_sha or sha(before) != adopt_sha:
                raise ValueError('Now has manual changes. Preserve/reconcile them before refresh; nothing overwritten')
            archive = vault / '00_System' / ('Now 이전 보드 ' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.md')
            # Same directory preserves existing relative links exactly.
            with archive.open('xb') as stream:
                stream.write(before)
        rows = projects(vault)
        output = render(rows, limit).encode()
        if fingerprint(projects(vault)) != fingerprint(rows):
            raise ValueError('Project state changed during generation; retry refresh')
        if (path.read_bytes() if path.exists() else b'') != before:
            raise ValueError('Now changed concurrently; nothing overwritten')
        if output != before:
            atomic_write(path, output)
        return dict(bytes=len(output), projects=len(rows), active=sum(not r['done'] for r in rows),
                    completed=sum(r['done'] for r in rows), legacy=[r['path'] for r in rows if r['legacy']],
                    changed=output != before)


def resume(rows, query):
    def normal(s):
        return re.sub(r'[\W_]+', '', str(s)).casefold()
    needle = normal(query)
    if not needle:
        raise ValueError('Provide a nonempty project alias')
    exact, partial = [], []
    for row in rows:
        names = [normal(n) for n in [row['project'], row['short'], *row.get('aliases', [])]]
        if needle in names:
            exact.append(row)
        elif any(needle in n for n in names):
            partial.append(row)
    return exact or partial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, default=DEFAULT_VAULT)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['refresh', 'preview', 'check']:
        p = sub.add_parser(name)
        p.add_argument('--max-bytes', type=int, default=4096)
        if name == 'refresh':
            p.add_argument('--adopt-sha', help='Explicit migration of a reconciled manual board; archives exact original')
    sub.add_parser('resume').add_argument('query')
    args = parser.parse_args()
    try:
        if args.command == 'refresh':
            value = refresh(args.vault, args.max_bytes, args.adopt_sha)
        else:
            rows = projects(args.vault)
            if args.command == 'preview':
                print(render(rows, args.max_bytes), end='')
                return 0
            if args.command == 'resume':
                value = resume(rows, args.query)
                if not value:
                    print('No state match. Read 30_Projects/Index.md before searching.')
                    return 1
            else:
                current = (args.vault / '00_System/Now.md').read_text()
                if current != render(rows, args.max_bytes):
                    raise ValueError('Now is stale or manually changed; inspect then refresh')
                value = dict(ok=True, bytes=len(current.encode()), projects=len(rows),
                             legacy=[r['path'] for r in rows if r['legacy']])
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return 0
    except (ValueError, OSError, yaml.YAMLError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
