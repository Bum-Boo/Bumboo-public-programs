#!/usr/bin/env python3
"""Reversible user install. Owns only recorded files and its dedicated virtualenv."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
import venv
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    args = parser.parse_args()
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    root = data / "grimoire"
    marker = root / "installation.json"
    runtime = root / "venv"
    source = Path(__file__).resolve().parents[1]
    launcher = args.bin_dir.absolute() / "grimoire"
    desktop = data / "applications/grimoire.desktop"
    icon = data / "icons/hicolor/scalable/apps/grimoire.svg"
    readme = root / "README.md"
    managed = [launcher, desktop, icon, readme]
    previous = json.loads(marker.read_text()) if marker.exists() else None
    if previous and previous.get("installer") != "grimoire-user-v1":
        raise SystemExit("Unknown installation marker; existing files preserved")
    if args.uninstall:
        if not previous:
            raise SystemExit("No managed installation found; nothing removed")
        stop(runtime)
        for path in managed:
            if path.is_file() and previous["files"].get(str(path)) == digest(path):
                path.unlink()
            elif path.exists():
                print(f"Preserved modified file: {path.name}")
        if runtime.is_dir() and not runtime.is_symlink():
            shutil.rmtree(runtime)
        marker.unlink()
        print("Application removed. Personal settings, skins and logs were preserved.")
        return
    for path in managed:
        if path.exists() and (not previous or previous["files"].get(str(path)) != digest(path)):
            raise SystemExit(f"Existing unowned or modified file preserved: {path}")
    if runtime.exists() and not previous:
        raise SystemExit("Unowned runtime directory preserved")
    if runtime.is_symlink():
        raise SystemExit("Runtime directory must not be a symlink")
    if previous:
        stop(runtime)
    root.mkdir(parents=True, exist_ok=True)
    try:
        if not (runtime / "bin/python").is_file():
            venv.EnvBuilder(with_pip=True).create(runtime)
        subprocess.run(
            [str(runtime / "bin/python"), "-m", "pip", "install", str(source)], check=True
        )
    except (subprocess.CalledProcessError, OSError):
        if not previous and runtime.is_dir() and not runtime.is_symlink():
            shutil.rmtree(runtime)
        raise
    for path in managed:
        path.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(runtime / "bin/grimoire")) + ' "$@"\n')
    launcher.chmod(0o755)
    shutil.copyfile(source / "src/grimoire/assets/grimoire.svg", icon)
    shutil.copyfile(source / "README.md", readme)
    escaped = str(launcher).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=Grimoire\n"
        "Comment=Desktop companion for agent work and music\n"
        f'Exec="{escaped}"\nIcon={icon}\nTerminal=false\n'
        "Categories=Utility;\nStartupWMClass=Grimoire\n"
    )
    marker.write_text(
        json.dumps(
            {
                "installer": "grimoire-user-v1",
                "files": {str(path): digest(path) for path in managed},
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Installed. Open Grimoire from the app menu or run {launcher}.")


def stop(runtime):
    command = runtime / "bin/grimoire"
    if command.exists():
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "grimoire"
        process = None
        try:
            pid = int((state / "instance.lock").read_text().splitlines()[0])
            candidate = Path(f"/proc/{pid}/exe")
            if candidate.resolve(strict=True) == (runtime / "bin/python").resolve():
                process = candidate
        except (OSError, ValueError, IndexError):
            pass
        subprocess.run([str(command), "quit"], timeout=5, check=True)
        deadline = time.monotonic() + 6

        def still_running():
            # Qt removes the socket before Python finishes releasing its executable.
            return (state / "control.sock").exists() or (process is not None and process.exists())

        while still_running() and time.monotonic() < deadline:
            time.sleep(0.1)
        if still_running():
            raise SystemExit("App has not stopped; existing installation preserved")


if __name__ == "__main__":
    main()
