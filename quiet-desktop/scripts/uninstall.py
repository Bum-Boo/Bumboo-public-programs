#!/usr/bin/python
"""Remove only Freiren Quiet; power-profiles-daemon and the recovery snapshot remain."""

import os
import shutil
import subprocess
from pathlib import Path


def main():
    if os.geteuid() != 0:
        raise SystemExit("sudo로 실행하세요.")
    subprocess.run(["systemctl", "disable", "--now", "freiren-quiet.service"], check=True)
    # Restore explicitly even if the daemon was already inactive or previously crashed.
    import sys

    sys.path.insert(0, "/usr/lib/freiren-quiet")
    import json

    from freiren_quiet.hardware import Hardware
    from freiren_quiet.power import PowerProfiles

    baseline = json.loads(Path("/var/lib/freiren-quiet/baseline.json").read_text())
    try:
        PowerProfiles().set(baseline.get("power_profile") or "balanced")
    finally:
        Hardware().restore(baseline)
    for filename in (
        "/usr/bin/freiren-quiet",
        "/etc/systemd/system/freiren-quiet.service",
        "/usr/share/applications/io.github.BumBoo.FreirenQuiet.desktop",
        "/etc/freiren-quiet/config.json",
    ):
        Path(filename).unlink(missing_ok=True)
    installed = Path("/usr/lib/freiren-quiet")
    if installed.is_dir() and not installed.is_symlink():
        shutil.rmtree(installed)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("CPU 설정을 복원하고 Freiren Quiet를 제거했습니다.")
    print("전력 관리 도구와 /var/lib/freiren-quiet의 복원 지점은 보존했습니다.")


if __name__ == "__main__":
    main()
