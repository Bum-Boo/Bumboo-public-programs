"""Local source selection; no hosts or credentials are accessed."""
import os
import fnmatch
import subprocess
from pathlib import Path

SKIP_DIRS = {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__',
             '.next', '.nuxt', '.cache', '.tox', '.mypy_cache', '.pytest_cache',
             '.ssh', '.aws', '.azure', '.gnupg', '.codex', '.claude', '.hermes',
             '.terraform', '.kube'}
SKIP_FILES = ['.env*', '*.pem', '*.key', '*.p12', '*.pfx', '*.keystore',
              '*credentials*', '*service-account*.json', 'id_rsa*', 'id_ed25519*',
              '.npmrc', '.netrc', '.pypirc', '.git-credentials', '*oauth*token*']


def excluded(path):
    return any(part in SKIP_DIRS or any(fnmatch.fnmatch(part.lower(), p) for p in SKIP_FILES)
               for part in path.parts)


def source_files(source):
    """Honor Git ignores when available; always exclude caches, credentials, links."""
    git = subprocess.run(['git', '-C', str(source), 'rev-parse', '--is-inside-work-tree'],
                         capture_output=True)
    if git.returncode == 0:
        out = subprocess.run(['git', '-C', str(source), 'ls-files', '-z', '--cached',
                              '--others', '--exclude-standard', '--', '.'],
                             capture_output=True, check=True).stdout
        candidates = sorted({os.fsdecode(p) for p in out.split(b'\0') if p})
    else:
        candidates = []
        for parent, dirs, files in os.walk(source, followlinks=False):
            rel = Path(parent).relative_to(source)
            dirs[:] = [d for d in dirs if not excluded(rel / d) and not (Path(parent) / d).is_symlink()]
            candidates.extend(str(rel / f) for f in files)
        candidates.sort()
    for value in candidates:
        rel = Path(value)
        if rel.is_absolute() or '..' in rel.parts or excluded(rel):
            continue
        path = source / rel
        if any((source.joinpath(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
            continue
        if path.is_file():
            yield rel, path

