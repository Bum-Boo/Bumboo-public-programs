#!/usr/bin/env python3
"""Run reviewed local acceptance commands and keep evidence tied to source hashes."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(paths):
    return {str(Path(p).resolve()): digest(p) for p in paths}


def run(spec_path, output):
    spec_path = Path(spec_path).resolve()
    raw = spec_path.read_bytes()
    spec = json.loads(raw)
    checks = spec.get('checks')
    if not spec.get('goal') or not isinstance(checks, list) or not checks:
        raise ValueError('A goal and at least one observable check are required')
    seen = set()
    sources = {str(spec_path), str(Path(__file__).resolve())}
    for check in checks:
        name, cmd = check.get('id'), check.get('command')
        if not isinstance(name, str) or not name.replace('-', '').replace('_', '').isalnum() or name in seen:
            raise ValueError('Check IDs must be unique simple names')
        seen.add(name)
        if not check.get('claim') or not isinstance(cmd, list) or not cmd or not all(isinstance(s, str) for s in cmd):
            raise ValueError(f'Invalid command/claim: {name}')
        if not Path(check.get('cwd', '')).is_absolute() or not Path(check['cwd']).is_dir():
            raise ValueError(f'Existing absolute cwd required: {name}')
        if not check.get('sources') or not all(Path(p).is_absolute() and Path(p).is_file() for p in check['sources']):
            raise ValueError(f'Existing absolute source files required: {name}')
        if not 0 < check.get('timeout_seconds', 60) <= 600:
            raise ValueError('Timeout must be between 0 and 600 seconds')
        sources.update(check['sources'])
    before = capture(sorted(sources))
    if before[str(spec_path)] != hashlib.sha256(raw).hexdigest():
        raise ValueError('Spec changed while preparing commands; retry from current spec')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    results = []
    for check in checks:
        started = time.monotonic()
        result = {k: check[k] for k in ['id', 'claim', 'command', 'cwd']}
        log = output / (check['id'] + '.log')
        with log.open('xb') as stream:
            try:
                proc = subprocess.Popen(check['command'], cwd=check['cwd'], stdin=subprocess.DEVNULL,
                                        stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = proc.wait(timeout=check.get('timeout_seconds', 60))
                    result.update(status='passed' if code == 0 else 'failed', exit_code=code)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    result.update(status='timeout', exit_code=None)
            except OSError as error:
                stream.write(str(error).encode())
                result.update(status='error', exit_code=None)
        result.update(seconds=round(time.monotonic() - started, 3), log=str(log), log_sha256=digest(log))
        results.append(result)
    after = {p: digest(p) if Path(p).is_file() else None for p in before}
    value = dict(schema=1, goal=spec['goal'], at=dt.datetime.now(dt.timezone.utc).isoformat(),
                 spec=str(spec_path), source_hashes=before, source_changed=before != after, checks=results)
    value['passed'] = not value['source_changed'] and all(r['status'] == 'passed' for r in results)
    (output / 'result.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return value


def fresh(result_path):
    value = json.loads(Path(result_path).read_text())
    if not value.get('passed') or not value.get('checks') or not value.get('source_hashes'):
        return False
    for path, wanted in value['source_hashes'].items():
        if not Path(path).is_file() or digest(path) != wanted:
            return False
    return all(r['status'] == 'passed' and Path(r['log']).is_file() and digest(r['log']) == r['log_sha256'] for r in value['checks'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='verb', required=True)
    p = sub.add_parser('run'); p.add_argument('spec', type=Path); p.add_argument('--out', type=Path, required=True)
    sub.add_parser('check').add_argument('result', type=Path)
    args = parser.parse_args()
    try:
        if args.verb == 'run':
            value = run(args.spec, args.out)
            print(json.dumps({'passed': value['passed'], 'checks': len(value['checks']), 'result': str(args.out / 'result.json')}))
            return 0 if value['passed'] else 1
        ok = fresh(args.result)
        print(json.dumps({'evidence_current': ok}))
        return 0 if ok else 1
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
