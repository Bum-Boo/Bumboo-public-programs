#!/usr/bin/env python3
"""Append only this workflow's Claude hooks; retain all preexisting settings."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import shlex
import sys

from agent_task import atomic_write, json_text


def install(settings_path=None, backup_root=None):
    settings_path = Path(settings_path or Path.home() / '.claude/settings.json')
    original = settings_path.read_bytes()
    before = json.loads(original)
    after = copy.deepcopy(before)
    hooks = after.setdefault('hooks', {})
    command = shlex.join([sys.executable, str(Path(__file__).with_name('agent-task-claude.py'))])
    changed = []
    for event in ('SessionStart', 'PreCompact', 'Stop', 'SessionEnd'):
        groups = hooks.setdefault(event, [])
        if any(hook.get('command') == command for group in groups for hook in group.get('hooks', [])):
            continue
        groups.append({'hooks': [{'type': 'command', 'command': command, 'timeout': 5}]})
        changed.append(event)
    if not changed:
        return {'changed': [], 'settings': str(settings_path)}
    if before.get('permissions') != after.get('permissions'):
        raise RuntimeError('Unexpected permission change')
    for key, value in before.items():
        if key != 'hooks' and after.get(key) != value:
            raise RuntimeError('Unexpected setting change: ' + key)
    for event, groups in before.get('hooks', {}).items():
        if after['hooks'].get(event, [])[:len(groups)] != groups:
            raise RuntimeError('An existing hook would be changed: ' + event)
    backup_root = Path(backup_root or Path.home() / '.local/share/agent-task/backups')
    backup = backup_root / datetime.now().strftime('%Y%m%d-%H%M%S-%f') / '.claude/settings.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(settings_path, backup)
    mode = stat.S_IMODE(settings_path.stat().st_mode)
    if settings_path.read_bytes() != original:
        raise RuntimeError('Settings changed concurrently; reread and retry without overwriting')
    atomic_write(settings_path, json_text(after))
    os.chmod(settings_path, mode)
    return {'changed': changed, 'settings': str(settings_path), 'backup': str(backup),
            'existing_hooks_preserved': sum(len(groups) for groups in before.get('hooks', {}).values()),
            'permissions_preserved': True}


if __name__ == '__main__':
    print(json.dumps(install(), ensure_ascii=False, indent=2))
