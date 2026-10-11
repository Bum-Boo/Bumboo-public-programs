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
        "gtk3",
    )
    # On upgrade the old daemon restores settings before its files are replaced.
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "freiren-quiet.service"],
            check=False,
        ).returncode
        == 0
    )
    if active:
        run("systemctl", "stop", "freiren-quiet.service")
    destination = Path("/usr/lib/freiren-quiet")
    for source in sorted((SOURCE / "freiren_quiet").glob("*.py")):
        install_file(source, destination / "freiren_quiet" / source.name)
    install_file(SOURCE / "launcher.py", destination / "launcher.py")
    install_file(SOURCE / "packaging/freiren-quiet", "/usr/bin/freiren-quiet", 0o755)
    install_file(
        SOURCE / "packaging/freiren-quiet.service", "/etc/systemd/system/freiren-quiet.service"
    )
    install_file(
        SOURCE / "packaging/io.github.BumBoo.FreirenQuiet.desktop",
        "/usr/share/applications/io.github.BumBoo.FreirenQuiet.desktop",
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
                f"설치 완료: {args.user} / {status['mode_label']} / CPU 상한 {status['limits']['max_perf_pct']}%"
            )
            return
        except (OSError, RuntimeError):
            time.sleep(0.5)
    raise RuntimeError("서비스 시작 확인 실패. journalctl -u freiren-quiet -n 30 로 확인하세요.")


if __name__ == "__main__":
    main()
