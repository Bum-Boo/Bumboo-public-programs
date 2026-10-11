#!/usr/bin/python
"""Install trusted source as root-owned files. Invoke with sudo and an explicit local user."""

import argparse
import grp
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from freiren_quiet.hardware import Hardware, atomic_json  # noqa: E402


def run(*args):
    subprocess.run(args, check=True)


def install_file(source, destination, mode=0o644):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(mode)
    os.chown(destination, 0, 0)


class Deployment:
    """Keep a root-only copy of installed code and settings for failed upgrades."""

    def __init__(self, state, paths):
        self.backup = Path(tempfile.mkdtemp(prefix="upgrade-", dir=state))
        self.entries = []
        for index, path in enumerate(paths):
            path = Path(path)
            saved = self.backup / str(index)
            exists = path.exists()
            if exists:
                if path.is_dir():
                    shutil.copytree(path, saved)
                else:
                    shutil.copy2(path, saved)
            self.entries.append((path, saved, exists))
        atomic_json(
            self.backup / "manifest.json",
            {str(p): s.name if e else None for p, s, e in self.entries},
        )

    def restore(self):
        for path, saved, existed in self.entries:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            if existed:
                if saved.is_dir():
                    shutil.copytree(saved, path)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(saved, path)


def main():
    parser = argparse.ArgumentParser(description="Freiren Quiet 설치/업데이트 (Arch Linux)")
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("sudo로 실행해야 합니다.")
    user = pwd.getpwnam(args.user)
    if user.pw_uid == 0:
        parser.error("데스크톱을 사용하는 일반 계정을 지정하세요.")
    grp.getgrgid(user.pw_gid)
    hardware = Hardware()
    hardware.validate()
    state = Path("/var/lib/freiren-quiet")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.chmod(0o700)
    # Capture before installing/starting PPD: installation itself may change EPP.
    baseline = state / "baseline.json"
    if not baseline.exists():
        snapshot = hardware.snapshot()
        snapshot["power_profile"] = None
        active = (
            subprocess.run(
                ["systemctl", "is-active", "--quiet", "power-profiles-daemon"],
                check=False,
            ).returncode
            == 0
        )
        snapshot["ppd_was_active"] = active
        if active:
            from freiren_quiet.power import PowerProfiles

            snapshot["power_profile"] = PowerProfiles().current()
        atomic_json(baseline, snapshot)
    else:
        stored = json.loads(baseline.read_text())
        if stored["identity"] != hardware.identity():
            raise RuntimeError("기존 설치의 하드웨어가 다릅니다.")

    run(
        "pacman",
        "-S",
        "--needed",
        "--noconfirm",
        "power-profiles-daemon",
        "python-psutil",
        "python-gobject",
    )
    # On upgrade the old daemon restores settings before its files are replaced.
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "freiren-quiet.service"],
            check=False,
        ).returncode
        == 0
    )
    destination = Path("/usr/lib/freiren-quiet")
    original_baseline = baseline.read_bytes()
    deployment = Deployment(
        state,
        (
            destination,
            Path("/usr/bin/freiren-quiet"),
            Path("/etc/systemd/system/freiren-quiet.service"),
            Path("/etc/freiren-quiet/config.json"),
            state / "settings.json",
        ),
    )
    if active:
        run("systemctl", "stop", "freiren-quiet.service")
    try:
        deploy(user, destination)
        if baseline.read_bytes() != original_baseline:
            raise RuntimeError("기존 복원 지점이 변경되었습니다.")
        print("기존 CPU 복원 지점 보존 확인")
    except Exception:
        subprocess.run(["systemctl", "stop", "freiren-quiet.service"], check=False)
        deployment.restore()
        run("systemctl", "daemon-reload")
        if active:
            run("systemctl", "start", "freiren-quiet.service")
        print(f"업데이트를 되돌렸습니다. 복구 사본: {deployment.backup}", file=sys.stderr)
        raise


def deploy(user, destination):
    for source in sorted((SOURCE / "freiren_quiet").glob("*.py")):
        install_file(source, destination / "freiren_quiet" / source.name)
    install_file(SOURCE / "launcher.py", destination / "launcher.py")
    install_file(SOURCE / "packaging/freiren-quiet", "/usr/bin/freiren-quiet", 0o755)
    install_file(
        SOURCE / "packaging/freiren-quiet.service", "/etc/systemd/system/freiren-quiet.service"
    )
    atomic_json(
        Path("/etc/freiren-quiet/config.json"),
        {
            "allowed_uid": user.pw_uid,
            "allowed_gid": user.pw_gid,
        },
    )
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "power-profiles-daemon.service")
    run("systemctl", "enable", "--now", "freiren-quiet.service")
    from freiren_quiet.client import request

    for _ in range(20):
        try:
            status = request()
            if status["error"]:
                raise RuntimeError(status["error"])
            print(
                f"설치 완료: {user.pw_name} / {status['mode_label']} / CPU 상한 {status['limits']['max_perf_pct']}%"
            )
            # The controller owns the GUI; remove the old standalone entry only after verification.
            Path("/usr/share/applications/io.github.BumBoo.FreirenQuiet.desktop").unlink(
                missing_ok=True
            )
            (destination / "freiren_quiet/gui.py").unlink(missing_ok=True)
            return
        except (OSError, RuntimeError):
            time.sleep(0.5)
    raise RuntimeError("서비스 시작 확인 실패. journalctl -u freiren-quiet -n 30 로 확인하세요.")


if __name__ == "__main__":
    main()
